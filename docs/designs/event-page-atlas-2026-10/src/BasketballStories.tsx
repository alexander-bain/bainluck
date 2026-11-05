import {reconcileReaderSelection} from './readerSelection';
import {useEffect,useRef} from 'react';
import {nbaProjectionUnavailable,nbaMarginTitle} from './basketballProjectionAvailability';
import {nbaMountedBaselineUnavailable} from './basketballBaselineAvailability';
import {basketballFamilies as families,basketballMomentOrder,type BasketballFamily as Family} from './basketballMomentStories';
import {createStoryStream,holdStories,selectStory,type StoryStreamState} from './storyStreamState';
import {eventReaderTime} from './eventReaderTime';
import {useStoryReaderMemory} from './StorySession';
import {type Dispatch,type SetStateAction} from 'react';
import {StoryStream} from './StoryStream';
import {useStoryState} from './StorySession';
import type {Row} from './Atlas';
import type {CatalogAnchor} from './catalogSelection';
import {groupCatalogRows} from './catalogGroups';
import {marginEligible} from './marginPregame';
import {MarginExpectationVisual} from './MarginExpectationVisual';
import {CatalogProbabilityCard} from './CatalogProbabilityCard';
import {catalogPresentation} from './probabilityPresentation';
import {totalPregameRecord} from './totalPregame';
import {TotalExpectationCard} from './TotalExpectationCard';
import {finalHeaderFor} from './FinalOutcomeHeader';
import {probabilityLabel} from './probabilityLabel';
import {CardFocus,ExpandCard} from './CardFocus';
import {useKeyboard} from './mobile';
import './basketballFocus.css';
export function BasketballStories({rows,mode,onPick,anchors,setAnchors,wide,large}:{rows:Row[];mode:string;onPick:(row:Row)=>void;anchors:Record<string,CatalogAnchor<Row>>;setAnchors:Dispatch<SetStateAction<Record<string,CatalogAnchor<Row>>>>;wide:boolean;large:boolean}){
 const originalRank=basketballMomentOrder();
 const rank=nbaProjectionUnavailable?{ids:(nbaMountedBaselineUnavailable?["margin","totals"]:["totals","margin"]) as Family[],reasons:{} as Partial<Record<Family,string>>,selectedTotalKey:originalRank.selectedTotalKey}:nbaMountedBaselineUnavailable?{ids:["margin","totals","forecast"] as Family[],reasons:{} as Partial<Record<Family,string>>,selectedTotalKey:originalRank.selectedTotalKey}:originalRank;
 const [stream,setStream]=useStoryState<StoryStreamState>('nba','stream',()=>createStoryStream(rank.ids));
 const [readerOrder,setReaderOrder]=useStoryState<string[]>('nba','readerOrder',[]);
 const [admittedOrder,setAdmittedOrder]=useStoryState<string[]|null>('nba','admittedOrder',null);
 const ordered=(admittedOrder??rank.ids).flatMap(id=>{const card=families.find(c=>c.id===id);return card?[card]:[]});
 const memory=useStoryReaderMemory('nba');
 const keyboard=useKeyboard();
 const [focus,setFocus]=useStoryState<Family|null>('nba','focus',null);
 const [readerActive,setReaderActive]=useStoryState<string|null>('nba','readerActive',null);
 const [returnOrigin,setReturnOrigin]=useStoryState<string|null>('nba','returnOrigin',null);
 const [pendingOrder,setPendingOrder]=useStoryState<string[]|null>('nba','pendingReaderOrder',null);
 const activeRef=useRef(readerActive);activeRef.current=readerActive;
 // Isolated order/removal replay only. Retained scores/prices/details are untouched.
 const replay=new URLSearchParams(window.location.search).get('readerReplay');
 useEffect(()=>{
  if(focus===null||!['reverse','remove','empty'].includes(replay??''))return;
  const timer=setTimeout(()=>setPendingOrder(replay==='empty'?[]:replay==='reverse'?[...readerOrder].reverse():readerOrder.filter(id=>id!==activeRef.current)),1400);
  return()=>clearTimeout(timer);
 },[focus,replay]);
 const refreshReader=()=>{
  if(pendingOrder===null)return;
  const next=[...pendingOrder];
  setReaderActive(reconcileReaderSelection(readerOrder,readerActive,next));
  setReturnOrigin(reconcileReaderSelection(readerOrder,returnOrigin,next));
  setReaderOrder(next);setAdmittedOrder(next);setPendingOrder(null);
  setStream(s=>({...holdStories(s),order:next,active:reconcileReaderSelection(s.order,s.active,next),pending:null}));
 };
 const totals=rows.filter(row=>totalPregameRecord(row)).sort((a,b)=>a.threshold!-b.threshold!);
 const [milestone,setMilestone]=useStoryState('nba','milestone',()=>totals.find(row=>row.key===rank.selectedTotalKey)?.key??totals[4]?.key);
 const [timing,setTiming]=useStoryState('nba','timing',{margin:false,totals:false});
 const margin=groupCatalogRows(rows).find(group=>marginEligible(group.rows,'completed'));
 const header=finalHeaderFor('nba')!;
 const expand=(id:Family)=>{keyboard.hide();setStream(s=>selectStory(s,id));setReaderOrder([...stream.order]);setReaderActive(id);setReturnOrigin(id);setPendingOrder(null);setFocus(id)};
 const activateReader=(id:string)=>{setReaderActive(id);setStream(s=>selectStory(s,id))};
 const readerCards=(focus!==null?readerOrder:stream.order).flatMap(id=>{const card=families.find(c=>c.id===id);return card?[card]:[]});
 const pick=(row:Row)=>{setStream(s=>{const id=totalPregameRecord(row)?'totals':margin?.rows.some(r=>r.key===row.key)?'margin':null;return focus===null&&id?selectStory(s,id):holdStories(s)});onPick(row)};
 const context={status:'completed',qualityHold:false,mode};
 const story=(id:Family)=>id==='forecast'?<BasketballScoreForecast/>:id==='totals'?<TotalExpectationCard rows={totals} onPick={pick} selectedKey={milestone} onSelection={setMilestone} timingOpen={timing.totals} onTimingOpen={value=>setTiming(old=>old.totals===value?old:{...old,totals:value})}/>:margin?<CatalogProbabilityCard rows={margin.rows} context={context} savedAnchor={anchors[margin.key]??null} onSelection={anchor=>setAnchors(old=>old[margin.key]?.row===anchor.row?old:{...old,[margin.key]:anchor})} onPick={pick} displayTitle={nbaMarginTitle} baselineInVisual selectedSummaryInVisual selectionControlsInVisual visual={(selected,choose)=><MarginExpectationVisual rows={margin.rows} visibleRows={margin.rows} selected={selected} state={catalogPresentation(selected,context)} choose={choose} timingOpen={timing.margin} onTimingOpen={value=>setTiming(old=>old.margin===value?old:{...old,margin:value})}/>}/>:null;
 return <><StoryStream event="nba" wide={wide} requireCardVisibility resumeAfterScroll basis={nbaProjectionUnavailable?"Recorded final · pregame score projection unavailable":nbaMountedBaselineUnavailable?"Recorded final · pregame prop chances unavailable":"Recorded final · ranked from this game's outcome"} readerOpen={focus!==null} cards={ordered.map(card=>({...card,visual:<div className="basketball-story-slot"><ExpandCard label={card.name} onClick={()=>expand(card.id)}/>{rank.reasons[card.id]&&<p className="basketball-moment-reason">{rank.reasons[card.id]}</p>}{story(card.id)}</div>}))}/>
 <CardFocus memory={memory} start={focus} resumeAt={readerActive} onActiveCardChange={activateReader} cards={readerCards.map(card=>({...card,visual:<div className={`basketball-focus-content ${large?'large-text':''}`}>{story(card.id)}</div>}))} refreshControl={pendingOrder!==null?<div className="cf-refresh"><span role="status">Card update ready</span><button onClick={refreshReader}>Refresh cards</button></div>:undefined} onClose={()=>{setStream(s=>returnOrigin?selectStory(s,returnOrigin):holdStories(s));setPendingOrder(null);setFocus(null)}} wide={wide} large={large} returnLabel="Back to match" anchor={<><b>Clippers {header.homeScore}–{header.awayScore} Warriors · Final</b><span>Pregame · opening win chance · Clippers {probabilityLabel(header.homeBaseline)} / Warriors {probabilityLabel(header.awayBaseline)}</span></>}/>
 </>;
}

function BasketballScoreForecast(){
 const h=finalHeaderFor('nba')!;
 const teams=[{name:'Clippers',actual:h.homeScore,forecast:h.projectedHome!,color:'var(--series-home)'},{name:'Warriors',actual:h.awayScore,forecast:h.projectedAway!,color:'var(--series-away)'}];
 const low=Math.floor((Math.min(...teams.map(t=>t.actual))-5)/10)*10,high=Math.ceil((Math.max(...teams.map(t=>t.forecast))+5)/10)*10;
 const x=(value:number)=>60+(value-low)/(high-low)*254;
 return <article className="atlas-card basketball-score-forecast"><span className="eyebrow">Points · performance versus expectation</span><h3>Both teams finished below their forecast</h3>
 <svg viewBox="0 0 344 280" role="img" aria-label={teams.map(t=>`${t.name}: pregame projected ${t.forecast} points, actual final ${t.actual}; ${(t.forecast-t.actual).toFixed(1)} points below forecast`).join('; ')}>
  {teams.map((t,i)=>{const y=74+i*126;return <g key={t.name} style={{color:t.color}}><text x="14" y={y-46} className="basketball-team">{t.name}</text><line x1={x(low)} x2={x(high)} y1={y} y2={y} className="basketball-score-track"/><line x1={x(t.actual)} x2={x(t.forecast)} y1={y} y2={y} stroke="currentColor" strokeWidth="3"/><rect x={x(t.forecast)-5} y={y-5} width="10" height="10" fill="white" stroke="currentColor" strokeWidth="2"/><line x1={x(t.actual)} x2={x(t.actual)} y1={y-11} y2={y+11} stroke="currentColor" strokeWidth="3"/><text x={x(t.forecast)} y={y-20} textAnchor="middle" className="basketball-number">{t.forecast}</text><text x={x(t.actual)} y={y+33} textAnchor="middle" className="basketball-number">{t.actual}</text><text x="330" y={y-46} textAnchor="end" className="basketball-delta">{(t.actual-t.forecast).toFixed(1)} points</text></g>})}
  {Array.from({length:(high-low)/10+1},(_,i)=>low+i*10).map(t=><text key={t} x={x(t)} y="264" textAnchor="middle" className="basketball-axis">{t}</text>)}
 </svg>
 <p className="basketball-forecast-legend">□ Pregame projected final <span>┃ Actual final</span></p>
 <p className="atlas-note">Points axis · {low}–{high}. Forecast recorded {eventReaderTime.full(h.projectionAt)}. Final score observed {eventReaderTime.full(h.scoreAt)}.</p></article>;
}
