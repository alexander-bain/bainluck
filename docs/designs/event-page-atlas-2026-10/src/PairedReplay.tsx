import {NFLHistoryPlotSize} from './NFLHistoryPlotSize';
import {NFLHistoryReadout} from './NFLHistoryReadout';
import {nflHistoryInspection,selectNFLHistory} from './nflHistoryInspection';
import {NFLLineDetails} from './NFLLineDetails';
import {reconcileReaderSelection} from './readerSelection';
import {nflTimeline} from './nflTimeline';
import {eventReaderTime} from './eventReaderTime.ts';
import type {nflForecastPresentation} from './nflForecastValidity';
import './forecastValidity.css';
import {nflReadingFrame,nflReadingMoments} from './nflReadingFrame';
import type {useNFLReadingSession} from './NFLReadingSession';
import './soccerReadingFrame.css';
import {useEffect,useRef,useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {InfoCircledIcon,ChevronLeftIcon,ChevronRightIcon,PauseIcon,PlayIcon} from '@radix-ui/react-icons';
import * as Dialog from '@radix-ui/react-dialog';
import {ResponsiveContainer} from './ChartVisibility';
import {ComposedChart, Line, CartesianGrid, XAxis, YAxis, ReferenceLine, ReferenceDot, ScatterChart, Scatter} from 'recharts';
import {BottomSheet,MobileScroll,KeyboardInput,useKeyboard} from './mobile';
import {FinalVisualCatalog} from './FinalVisualCatalog';
import {useCatalogPageSession} from './useCatalogPageSession';
import {adaptFinalRows,type ArchivedFinalRow} from './finalCatalogEvidence';
import flags from './finalCatalogFlags.json';
import {nflGame as g,nflBaseline,nflMoments,nflContext,nflFinishCaption,nflRank,scoreClusters,type NFLCard} from './nflReplay';
import {ProfileChart} from './ExpectationProfiles';
import {TouchdownCard} from './VarietyCards';
import {probabilityLabel as pct} from './probabilityLabel';
import profiles from './profiles.json';
import rows from './markets.json';
import './movingFeed.css';
import './pairedReplay.css';
import {CardFocus,ExpandCard} from './CardFocus';

const catalogRows=adaptFinalRows(rows as ArchivedFinalRow[],flags);
const stamp=eventReaderTime.full;
type Context=ReturnType<typeof nflContext>;
type ForecastPresentation=ReturnType<typeof nflForecastPresentation>&{detailKey:string|null;setDetailKey:(key:string|null)=>void};
function FinishCard({c,forecast}:{c:Context;forecast:ForecastPresentation}){
 const pre=g.projections.filter(p=>Date.parse(p.timestamp)<Date.parse(g.commence_time)&&p.projected_home_score!==null).at(-1)!;
 const marks=[{team:'Bears',y:2,pre:pre.projected_home_score!,now:c.projection?.projected_home_score,actual:c.final?c.score?.home_score:null,color:'var(--series-home)'},{team:'Eagles',y:1,pre:pre.projected_away_score!,now:c.projection?.projected_away_score,actual:c.final?c.score?.away_score:null,color:'var(--series-away)'}];
 return <article className="mf-card pr-finish"><div className="mf-card-top"><span>{c.final?'Final vs forecast':'Projected finish'}</span></div><h2>{nflFinishCaption(c)}</h2><div className="pr-finish-plot" role="img" aria-label={marks.map(t=>`${t.team}: pregame projected ${t.pre} points; ${c.final?'final '+t.actual:c.projection?'recorded projection '+t.now+' points at '+stamp(c.projection.timestamp):'no recent projection'}`).join('; ')}><ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{left:0,right:20,top:22,bottom:16}}><XAxis dataKey="x" type="number" domain={[0,35]} ticks={[0,10,20,30]} axisLine={false} tickLine={false} tick={{fontSize:11}}/><YAxis dataKey="y" type="number" domain={[.3,2.7]} ticks={[1,2]} tickFormatter={v=>v===2?'Bears':'Eagles'} width={47} axisLine={false} tickLine={false} tick={{fontSize:12}}/>{marks.map(t=><Scatter key={t.team} data={[{x:t.pre,y:t.y}]} shape="square" fill="var(--surface-card)" stroke={t.color} strokeWidth={2} isAnimationActive={false}/>)}{marks.filter(t=>c.final?t.actual!=null:t.now!=null&&!c.pregame).map(t=><Scatter key={t.team+'new'} data={[{x:c.final?t.actual:t.now,y:t.y}]} shape={c.final?'cross':'square'} fill={t.color} isAnimationActive={false}/>)}</ScatterChart></ResponsiveContainer></div><div className="pr-finish-values">{marks.map(t=><div key={t.team}><span>{t.team}</span><b>{t.pre}<small>pregame projection</small></b>{!c.pregame&&<b>{c.final?t.actual:t.now??'—'}<small>{c.final?'final points':c.projection?'recorded projection':'No recent projection'}</small></b>}</div>)}</div><p className="mf-caption">Points · outline = pregame · {c.final?'cross = final':'filled square = later forecast'}</p>{forecast.historical&&<details className="fv-history" open={forecast.detailKey===forecast.historical.timestamp} onToggle={e=>{if(e.currentTarget.open)forecast.setDetailKey(forecast.historical!.timestamp);else if(forecast.detailKey===forecast.historical!.timestamp)forecast.setDetailKey(null)}}><summary>Earlier forecast · details</summary><p><strong>{forecast.historical.projected_home_score}–{forecast.historical.projected_away_score}</strong> · Bears–Eagles</p><p>Recorded {stamp(forecast.historical.timestamp)}. {forecast.expired?'Expired':'Valid until'} {stamp(forecast.historical.valid_until)}.</p><p>Historical only. The score and chart stay at your reading snapshot until you refresh.</p></details>}</article>
}
function NFLCardView({id,c,forecast,pick,rushSelection}:{id:NFLCard;c:Context;forecast:ForecastPresentation;pick:(key:string)=>void;rushSelection:{rowKey:string;onSelect:(key:string)=>void}}){
 return <div className="pr-card" data-nfl-card={id}>{id==='finish'?<FinishCard c={c} forecast={forecast}/>:id==='rush'?<ProfileChart profile={profiles[0]} final={c.final} onDetail={pick} selection={rushSelection}/>:<TouchdownCard final={c.final} onDetail={pick}/>}</div>
}
export function PairedReplayPage({wide,session}:{wide:boolean;session:ReturnType<typeof useNFLReadingSession>}){
 const keyboard=useKeyboard();
 const {scope,state,dispatch,catalogSession,reduced,hidden,expanded,setExpanded,readerActive,setReaderActive,returnOrigin,setReturnOrigin,details,setDetails,info,setInfo,catalog,setCatalog,large,setLarge,rushKey,setRushKey}=session;
 const forecast:ForecastPresentation={...session.forecast,detailKey:session.forecastDetailKey,setDetailKey:session.setForecastDetailKey};
 const [category,setCategory]=useState('All'),[query,setQuery]=useState(''),[search,setSearch]=useState(false),[limit,setLimit]=useState(12),[short,setShort]=useState(false),[visible,setVisible]=useState(false),[chartPassed,setChartPassed]=useState(false);
 const page=useRef<HTMLDivElement>(null),body=useRef<HTMLDivElement>(null);
 const returnToCard=useRef(false);
 const index=state.displayed.sequence,c=forecast.context,pending=state.received.sequence-index;
 const timeline=nflTimeline(c),domain=timeline.domain;
 const {historySelection,setHistorySelection,inspecting,setInspecting}=session;
 const historyTrigger=useRef<HTMLButtonElement>(null),returnHistoryFocus=useRef(false);
 const closeHistory=()=>{returnHistoryFocus.current=true;setInspecting(false)};
 useEffect(()=>{
  if(inspecting||!returnHistoryFocus.current)return;
  const host=page.current?.closest('.device-screen')??document.body;
  let frame:number|null=null;
  const restore=()=>{
   if(host.querySelector('.bottom-sheet,.cf-dialog,.nfl-history-dialog'))return;
   observer.disconnect();
   frame=requestAnimationFrame(()=>{historyTrigger.current?.focus({preventScroll:true});returnHistoryFocus.current=false});
  };
  const observer=new MutationObserver(restore);observer.observe(host,{childList:true,subtree:true});restore();
  return()=>{observer.disconnect();if(frame!==null)cancelAnimationFrame(frame)};
 },[inspecting]);
 const inspection=nflHistoryInspection(c,historySelection);
 const inspect=(index:number)=>{pause();setHistorySelection(selectNFLHistory(c,index));setInspecting(true)};
 const activeIndex=Math.max(0,state.stream.order.indexOf(state.stream.active??''));
 const ordered=[...state.stream.order.slice(activeIndex),...state.stream.order.slice(0,activeIndex)] as NFLCard[];
 const reading=!wide||short||large,open=info||details!==null,running=!state.stream.held&&!reduced&&!hidden&&!catalog&&!open&&expanded===null&&!inspecting&&visible;
 const pause=()=>dispatch({type:'hold'}),resume=()=>{keyboard.hide();dispatch({type:'resume',manual:reduced})};
 const pick=(key:string)=>{keyboard.hide();pause();setDetails(key)};
 const rushSelection={rowKey:rushKey,onSelect:(key:string)=>{pause();setRushKey(key)}};
 const advance=(next:number)=>dispatch({type:'inspect',frame:nflReadingFrame(next,scope)});
 const toChart=()=>{pause();body.current?.querySelector('.mobile-scroll')?.scrollTo({top:0,behavior:'instant'})};
 const toCards=()=>{pause();const scroller=body.current?.querySelector<HTMLElement>('.mobile-scroll'),anchor=scroller?.querySelector<HTMLElement>('.mf-anchor');if(scroller)scroller.scrollTo({top:anchor?.offsetHeight??0,behavior:'instant'})};
 const refreshReader=()=>{
  if(state.locks.some(lock=>lock!=='reader'))return;
  const next=state.received.order,previous=state.stream.order;
  setReturnOrigin(reconcileReaderSelection(previous,returnOrigin,next));
  setReaderActive(reconcileReaderSelection(previous,readerActive,next));
  dispatch({type:'refresh',selected:readerActive});
 };
 const expand=(id:NFLCard)=>{keyboard.hide();dispatch({type:'select',id});setReaderActive(id);setReturnOrigin(id);setExpanded(id)};
 useEffect(()=>{
  const root=page.current!;
  // Layout mode depends on the viewport, never the content it moves between modes.
  const measure=()=>setShort(root.clientHeight<900);
  const observer=new ResizeObserver(measure);observer.observe(root);measure();return()=>observer.disconnect();
 },[wide]);
 useEffect(()=>{const scroller=body.current!.querySelector('.mobile-scroll')!;const hold=()=>{dispatch({type:'hold'});const anchor=scroller.querySelector<HTMLElement>('.mf-anchor');setChartPassed(!!anchor&&scroller.scrollTop>=anchor.offsetHeight-1)};scroller.addEventListener('scroll',hold,{passive:true});return()=>scroller.removeEventListener('scroll',hold)},[dispatch]);
 // The sheet restores focus when its exit animation finishes. Seat the selected
 // card after that removal, so focus cannot pull the page back into the chart.
 useEffect(()=>{
  if(expanded!==null||!returnToCard.current)return;
  const host=page.current?.closest('.device-screen')??document.body;
  let frame:number|null=null;
  const restore=()=>{
   if(host.querySelector('.bottom-sheet,.cf-dialog,.nfl-history-dialog'))return;
   observer.disconnect();
   frame=requestAnimationFrame(()=>{
    const scroller=body.current?.querySelector<HTMLElement>('.mobile-scroll');
    const anchor=scroller?.querySelector<HTMLElement>('.mf-anchor');
    body.current?.querySelector<HTMLButtonElement>('.cf-expand')?.focus({preventScroll:true});
    scroller?.scrollTo({top:anchor?.offsetHeight??0,behavior:'instant'});
    returnToCard.current=false;
   });
  };
  const observer=new MutationObserver(restore);observer.observe(host,{childList:true,subtree:true});restore();
  return()=>{observer.disconnect();if(frame!==null)cancelAnimationFrame(frame)};
 },[expanded]);
 useEffect(()=>{const feed=body.current?.querySelector('.mf-feed');if(!feed){setVisible(false);return}const observer=new IntersectionObserver(entries=>setVisible(entries[0].isIntersecting),{root:body.current,threshold:.15});observer.observe(feed);return()=>observer.disconnect()},[catalog,wide]);
 useEffect(()=>{if(!running)return;const timer=setInterval(()=>dispatch({type:'move',delta:1,automatic:true}),10000);return()=>clearInterval(timer)},[running,dispatch]);
 const frameStatus=<div className="sr-frame-status" role="status"><div><strong>{state.stream.held?'Reading snapshot':'Following recorded updates'}</strong><span>Shown through {stamp(c.at)}{nflReadingMoments[index].kind==='expiry'?' · forecast validity boundary':''}</span></div>{pending>0&&<span className="sr-waiting">{pending} {pending===1?'update':'updates'} waiting</span>}</div>;
 const period=c.final?'Final':c.pregame?'Pregame':c.state?.game_state.period.replace(' - ',' · ')??'Clock unavailable';
 const baselinePair=[nflBaseline.home_probability,1-nflBaseline.home_probability];
 const selected=rows.find(r=>r.row_key===details);
 const content=info?<><h3>Two competitors, one match</h3><p>Bears–Eagles · September 28, 2026. Archived observations, not a live connection.</p><p>Every in-game probability pair comes directly from a retained game-state row. Pregame uses the retained NFL two-outcome contract. No terminal result was appended as a 100% quote. Breaks in the lines preserve gaps longer than five minutes between retained observations.</p><p>Selected observation: {stamp(c.at)}. Score: {c.score?stamp(c.score.timestamp):'not yet observed'}. Probability: {c.state?stamp(c.state.timestamp):stamp(nflBaseline.timestamp)}. The headline clock belongs to its observed game-state row.</p><p>{c.projection?`Projection recorded ${stamp(c.projection.timestamp)}, valid until ${stamp(c.projection.valid_until)}.`:'No current projection is admitted at this moment.'} Projection and win chance have separate source timestamps.</p><h4>Timeline context</h4><p>Quarter and halftime positions are first-observed boundaries, not exact whistle times. Score dots are observations, not exact scoring-play times. Nearby updates share a label; every original checkpoint is retained here.</p>{c.periods.map(p=><p key={p.timestamp}>{p.period}: after {stamp(p.not_before)} and by {stamp(p.timestamp)}.</p>)}{c.scores.map(s=><p key={s.timestamp}>{s.home_score}–{s.away_score} first observed {stamp(s.timestamp)}.</p>)}<h4>Reading snapshots</h4><p>The score, paired history, period context and cards stay at the shown cutoff while arrivals continue. Latest received: {stamp(state.received.through)}. {pending} updates waiting. Refresh in the reader applies the latest snapshot and order together, then keeps the cards paused. Closing a reader does not refresh.</p><p>Forecast validity advances independently of the held snapshot. At the recorded valid-until time, the headline and card clear the forecast even if no new match observation has arrived. The earlier forecast remains in card details. Validity clock: {forecast.horizon?stamp(forecast.horizon)+'':'unavailable'}. This replay uses an explicit simulated clock, not a live freshness connection.</p><h4>Card order</h4><p>This replay uses explicit editorial rules, not connected AI ranking. The finish forecast leads before the result; the unlikely passing-TD result leads after the final. Player cards keep pregame probabilities; player progress is unavailable before final. Novel combinations remain a later step.</p></>:<NFLLineDetails large={large} row={selected} at={c.at} final={c.final} conflict={details!==null&&(flags as Record<string,boolean>)[details]===true}/>;
 const historyPlot=(plotID:string)=><div className="mf-history pr-history" role="img" aria-label={`${timeline.label}. ${timeline.history.length} recorded observations. Bears and Eagles win chances. Pregame ${pct(baselinePair[0])} and ${pct(baselinePair[1])}; last recorded ${pct(c.point?.home)} and ${pct(c.point?.away)}. ${c.final?'Final result is separate from probability.':''}`}><NFLHistoryPlotSize><ComposedChart id={plotID} data={timeline.plotted} margin={{left:-25,right:12,top:24,bottom:0}}><CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 5"/><XAxis dataKey="time" type="number" domain={domain} ticks={timeline.ticks} tickFormatter={eventReaderTime.short} tick={{fontSize:11}} axisLine={false} tickLine={false}/><YAxis domain={[0,1]} ticks={[0,.5,1]} tickFormatter={v=>v*100+'%'} tick={{fontSize:11}} axisLine={false} tickLine={false}/>{c.periods.map(p=><ReferenceLine key={p.timestamp} x={Date.parse(p.timestamp)} stroke="var(--surface-border)" label={{value:p.period==='Halftime'?'HT':'Q'+p.period[0],position:'insideTopRight',fill:'var(--text-secondary)',fontSize:11}}/>)}{inspecting&&inspection.point&&<ReferenceLine x={inspection.point.t} stroke="var(--text-secondary)" strokeDasharray="3 3"/>}{inspecting&&inspection.point&&['home','away'].map((side,i)=><ReferenceDot key={'inspection-'+side} x={inspection.point!.t} y={i?inspection.point!.away:inspection.point!.home} r={5} fill="var(--surface-card)" stroke={i?'var(--series-away)':'var(--series-home)'} strokeWidth={2}/>)}<Line dataKey="home" name="Bears" stroke="var(--series-home)" strokeWidth={3} dot={false} connectNulls={false} isAnimationActive={false}/><Line dataKey="away" name="Eagles" stroke="var(--series-away)" strokeWidth={3} dot={false} connectNulls={false} isAnimationActive={false}/>{['home','away'].map((side,i)=><ReferenceDot key={side} x={timeline.baselineAt} y={baselinePair[i]} r={4} fill="var(--surface-card)" stroke={i?'var(--series-away)':'var(--series-home)'} strokeWidth={2}/>)}{!c.pregame&&c.point&&['home','away'].map((side,i)=><ReferenceDot key={side+'end'} x={c.point!.time} y={i?c.point!.away:c.point!.home} r={4} fill={i?'var(--series-away)':'var(--series-home)'}/>)}</ComposedChart></NFLHistoryPlotSize></div>;
 const historyAnchor=<><b>Bears {c.score?`${c.score.home_score}–${c.score.away_score}`:'vs'} Eagles · {period}</b><span>Pregame · Bears {pct(nflBaseline.home_probability)} / Eagles {pct(1-nflBaseline.home_probability)}</span>{pending>0&&<span>{pending} {pending===1?'update':'updates'} waiting · return to match to refresh</span>}</>;
 const historyVisual=<div className="nfl-history-focus">{historyPlot('nfl-focused-history')}<NFLHistoryReadout inspection={inspection} onSelect={inspect}/></div>;
 const headline=<header className="mf-anchor pr-anchor" onPointerDown={pause}><div className="mf-brand"><strong>Bain Luck<span>.</span></strong><div><button onClick={()=>setLarge(v=>!v)} aria-pressed={large}>Aa</button><button aria-label="About this match timeline" onClick={()=>setInfo(true)}><InfoCircledIcon/></button></div></div><div className="pr-stage"><span>NFL · RECORDED MATCH</span><b>{period}</b></div><div className="pr-scoreboard">{['Bears','Eagles'].map((team,i)=><div key={team} className={i?'pr-away':'pr-home'}><span>{team}</span><strong>{c.final?(i?'Lost':'Won'):pct(i?c.point?.away:c.point?.home)}</strong><small>{c.final?'Final result':c.pregame?'Pregame chance':'Recorded win chance'}</small>{!c.pregame&&<small>Pregame <b>{pct(baselinePair[i])}</b></small>}</div>)}<div className="pr-score"><b>{c.score?`${c.score.home_score}–${c.score.away_score}`:'vs'}</b><span>{c.final?'Final score':c.pregame?'Pregame':'Actual score'}</span></div></div><div className="pr-projection"><span>{c.final?'Pregame projected final':c.pregame?'Projected final · pregame':'Projected final · recorded'}</span><b>{c.final?'19.5–23':c.projection?`${c.projection.projected_home_score}–${c.projection.projected_away_score}`:'No recent projection'}</b></div><div className="pr-history-heading"><strong>{timeline.label}</strong><button ref={historyTrigger} aria-expanded={inspecting} onClick={()=>{pause();if(!historySelection)setHistorySelection(selectNFLHistory(c,inspection.points.length-1));setInspecting(true)}}>Inspect history</button><span>{eventReaderTime.range(domain[0],domain[1])}</span></div>{historyPlot('nfl-main-history')}{!c.pregame&&<div className="mf-score-timeline" role="img" aria-label={c.scores.map(s=>`${s.home_score}–${s.away_score} first observed ${stamp(s.timestamp)}`).join('; ')||'No score observations before kickoff'}><ResponsiveContainer width="100%" height="100%"><ComposedChart data={c.scores.map(s=>({time:Date.parse(s.timestamp),level:.5}))} margin={{left:-25,right:12,top:8,bottom:0}}><XAxis dataKey="time" type="number" domain={domain} hide/><YAxis dataKey="level" type="number" domain={[0,1]} width={60} tick={false} tickLine={false} axisLine={false}/>{scoreClusters(c.scores,wide?940:300,domain).map((s,i)=><ReferenceDot key={s.at} x={Date.parse(s.at)} y={i%2?.75:.25} r={3} fill="var(--text-primary)" label={{value:s.label+(s.count>1?' +':''),position:Date.parse(s.at)>domain[0]+(domain[1]-domain[0])*.85?'left':'right',fontSize:11,fill:'var(--text-primary)'}}/>)}</ComposedChart></ResponsiveContainer></div>}<div className="pr-legend"><span className="pr-home">Bears</span><span className="pr-away">Eagles</span><span>{c.pregame?'Last pregame quote ○':'Observed periods / scores'} <button aria-label="Explain timeline markers" onClick={()=>setInfo(true)}><InfoCircledIcon/></button></span></div>{reading&&!catalog&&<button className="pr-card-invitation" onClick={toCards}><svg viewBox="0 0 60 32" aria-hidden="true">{profiles[0].points.map((p,i)=><g key={p.row_key}><line x1={4+i*4.6} x2={4+i*4.6} y1={29} y2={29-p.p*25}/><circle cx={4+i*4.6} cy={29-p.p*25} r={1.6}/></g>)}</svg><span><b>Forecasts &amp; player chances</b><small>Explore 3 visual cards</small></span><span aria-hidden="true">↓</span></button>}</header>;
 const controls=<div className="mf-controls"><nav><button aria-pressed={!catalog} onClick={()=>{keyboard.hide();setCatalog(false)}}>For you</button><button aria-pressed={catalog} onClick={()=>{keyboard.hide();pause();setCatalog(true)}}>All props</button></nav><button className="mf-play" disabled={open||expanded!==null||catalog||(reduced&&pending===0)} onClick={()=>state.stream.held||reduced?resume():pause()} aria-label={reduced?'Apply recorded updates':state.stream.held?'Resume recorded updates':'Pause recorded updates'}>{state.stream.held||reduced?<PlayIcon/>:<PauseIcon/>}{reduced?'Apply updates':state.stream.held?'Resume':'Pause'}</button><button aria-label="Next card" onClick={()=>dispatch({type:'move',delta:1})}><ChevronRightIcon/></button></div>;
 const readingSummary=<div className="mf-reading-summary"><div><b>Bears {c.score?`${c.score.home_score}–${c.score.away_score}`:'vs'} Eagles · {period}</b><span>{c.final?'Bears won':`${c.pregame?'Pregame':'Recorded'} chances · ${pct(c.point?.home)} / ${pct(c.point?.away)}`}</span></div><button onClick={toChart}>Chart</button></div>;
 const readingTools=<div className="mf-reading-tools">{controls}</div>;
 return <div ref={page} className={`mf-page pr-page ${session.compact?'pr-compact-preview':''} ${wide?'mf-wide':''} ${large?'mf-large':''} ${reading?'mf-reading':''}`}>
 {!reading&&headline}{reading&&chartPassed&&readingSummary}
 {!reading&&controls}
 <div ref={body} className="mf-body-frame" onPointerDown={pause}><MobileScroll className="mf-body">{reading&&headline}<div className="mf-card-stage">{reading&&readingTools}{pending>0&&<div className="pr-pending" role="status">{pending} {pending===1?'update':'updates'} waiting · Resume when ready</div>}{catalog?<section className="pr-library"><div className="mf-library-top"><b>All props · 1,598 outcomes</b><button onClick={()=>{keyboard.hide();setSearch(v=>!v);setQuery('')}}>{search?'Close search':'Find a prop'}</button></div><div className="mf-categories">{['All','player_props','totals','team_totals','spreads','period_markets','other'].map(cat=><button key={cat} aria-pressed={category===cat} onClick={()=>{keyboard.hide();setCategory(cat);setLimit(12)}}>{({All:'All',player_props:'Players',totals:'Game points',team_totals:'Team points',spreads:'Margins',period_markets:'Periods',other:'More'})[cat]}</button>)}</div>{(search||wide)&&<KeyboardInput aria-label="Find a football prop" placeholder="Player, team or prop" value={query} onChange={e=>{setQuery(e.target.value);setLimit(12)}} onBlur={()=>keyboard.hide()}/>}<FinalVisualCatalog session={catalogSession} phase={c.final?'Final':c.pregame?'Before':'During'} query={query} category={category} limit={limit} onPick={r=>pick(r.row_key)} onReveal={r=>{keyboard.hide();setCategory('All');setQuery(`${r.market_name} ${r.outcome_name}`);setSearch(true);setLimit(12)}} onMore={()=>setLimit(n=>n+12)}/></section>:<><section className="mf-feed pr-feed" onPointerEnter={e=>{if(e.pointerType==='mouse')pause()}} onFocusCapture={pause} onWheel={pause}><AnimatePresence mode="popLayout" initial={false}>{ordered.slice(0,wide?3:1).map(id=><motion.div key={id} initial={{opacity:0,y:reduced?0:30}} animate={{opacity:1,y:0}} exit={{opacity:0,y:reduced?0:-30}} transition={{duration:reduced?0:.45}}><ExpandCard label={({finish:"projected finish",rush:"rushing milestones",touchdowns:"passing touchdowns"})[id]} onClick={()=>expand(id)}/><NFLCardView id={id} c={c} forecast={forecast} pick={pick} rushSelection={rushSelection}/></motion.div>)}</AnimatePresence></section></>}</div></MobileScroll></div>
 <div className="mf-replay-control"><button aria-label="Previous replay position" disabled={index===0} onClick={()=>advance(index-1)}><ChevronLeftIcon/></button><div><b>{period}</b><span>{stamp(c.at)} · {nflReadingMoments[index].kind==='expiry'?'forecast validity boundary':'recorded observation'}</span></div><button aria-label="Next replay position" disabled={index>=state.received.sequence} onClick={()=>advance(index+1)}><ChevronRightIcon/></button></div>
 {wide?<Dialog.Root open={inspecting} onOpenChange={v=>{if(!v)closeHistory()}}><Dialog.Portal><Dialog.Overlay className="cf-overlay"/><Dialog.Content className={`nfl-history-dialog ${large?'cf-large':''}`} aria-describedby={undefined} onCloseAutoFocus={e=>{e.preventDefault();historyTrigger.current?.focus({preventScroll:true})}}><Dialog.Title className="sr-only">Win probability history</Dialog.Title><header><button onClick={closeHistory}>Back to match</button><div>{historyAnchor}</div></header><div className="nfl-history-dialog-body">{historyVisual}</div></Dialog.Content></Dialog.Portal></Dialog.Root>:<CardFocus memory={session.readerMemory} start={inspecting?'history':null} onClose={closeHistory} wide={false} large={large} returnLabel="Back to match" readerTitle="Win probability history" anchor={historyAnchor} cards={[{id:'history',name:'Win probability history',visual:historyVisual}]}/>}

 <CardFocus returnLabel="Back to match" suspended={open} memory={session.readerMemory} start={expanded} resumeAt={readerActive} onActiveCardChange={setReaderActive} wide={wide} large={large} refreshControl={pending>0?<div className="cf-refresh"><span role="status">{pending} {pending===1?'update':'updates'} ready</span><button onClick={refreshReader}>Refresh match</button></div>:undefined} onClose={()=>{returnToCard.current=true;dispatch({type:'lock',name:'reader',active:false});setExpanded(null);if(returnOrigin)dispatch({type:'select',id:returnOrigin})}} anchor={<><b>Bears {c.score?`${c.score.home_score}–${c.score.away_score}`:'vs'} Eagles · {period}</b><span>{c.final?'Bears won · final result':`${c.pregame?'Pregame':'Recorded'} win chance · Bears ${pct(c.point?.home)} / Eagles ${pct(c.point?.away)}`}</span></>} cards={ordered.map(id=>({id,name:({finish:'Projected finish',rush:'Rushing milestones',touchdowns:'Passing touchdowns'})[id],visual:<>{frameStatus}<NFLCardView id={id} c={c} forecast={forecast} pick={pick} rushSelection={rushSelection}/></>}))}/>
 {wide?<Dialog.Root open={open} onOpenChange={v=>{if(!v){setInfo(false);setDetails(null)}}}><Dialog.Portal><Dialog.Overlay className="atlas-modal-overlay"/><Dialog.Content className="atlas-dialog" aria-describedby={undefined}><Dialog.Title className="sr-only">{info?'Match timeline':'Prop details'}</Dialog.Title><Dialog.Close className="sheet-done">Done</Dialog.Close><div className="mf-details">{content}</div></Dialog.Content></Dialog.Portal></Dialog.Root>:<BottomSheet open={open} onOpenChange={v=>{if(!v){setInfo(false);setDetails(null)}}} title={info?'Match timeline':'Prop details'}><button className="sheet-done" onClick={()=>{setInfo(false);setDetails(null)}}>Done</button><div className="mf-details">{content}</div></BottomSheet>}
 </div>
}
