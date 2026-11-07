import {rangeGestureProps} from './rangeGesture';
import {StoryStream} from './StoryStream';
import {CardFocus,ExpandCard} from './CardFocus';
import {useStoryState,useStoryReaderMemory} from './StorySession';
import {tennisFinalCards,type TennisFinalKind} from './tennisFinalFocus';
import {useKeyboard} from './mobile';
import {readerTime,readerClock,readerCrossesDay} from './readerTime';
import {TennisHandicapStory} from './TennisHandicapStory';
import {TennisPropChance} from './TennisPropChance';
import {tennisPropBaseline,tennisPropNote,tennisPropEvidence} from './tennisPropPregame';
import {HeadlineInfo} from './HeadlineInfo';
import './specializedHeadlines.css';
import './tennisProbabilityJourney.css';
import {PregameContext} from './PregameContext';
import {TennisScoreStory} from './TennisScoreOutcomeCard';
import type {Dispatch,SetStateAction} from 'react';
import {ResponsiveContainer} from './ChartVisibility';
import {LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine, ReferenceDot} from 'recharts';
import {ChevronRightIcon} from '@radix-ui/react-icons';
import f from './tennisFinal.json';
import {probabilityLabel as pct} from './probabilityLabel';
import './tennisFinal.css';

type Row={key:string;source_file:string;market_name:string;outcome_name:string;source:string;_market_id:number|string;[key:string]:unknown};

const rows=f.rows as Row[];
const group=(id:number)=>rows.filter(r=>r._market_id===id);
const names=['Fokina','Tiafoe'];

export function TennisFinalHeadlineFacts(){return <div className="capture-headline-facts tennis-final-facts">
 <section><h3>Pre-match expectation</h3><p>Fokina {pct(f.prematchHome)}; Tiafoe {pct(f.prematchAway)}. Kalshi match-winner snapshot recorded {readerTime(tennisPropEvidence.headline.at,{seconds:true})}, before the verified {readerTime(tennisPropEvidence.start)} start. These are not the separate opening sportsbook estimates.</p></section>
 <section><h3>Final score</h3><p>Fokina won {f.homeSets}–{f.awaySets} in sets. Games finished {f.homeGames}–{f.awayGames}; {f.totalGames} games in total. ESPN score captured {readerTime(f.scoreAt,{seconds:true})}.</p><p>No valid projected final is supplied. The 22.5-game opening line is a market threshold, not a projected score.</p></section>
 <section><h3>Recorded probability history</h3><p>{f.series.length} retained Bain Luck aggregate observations. Tiafoe is the complement of the supplied Fokina aggregate for this two-player match winner. Gaps over five minutes stay blank.</p><p>The genuine 89.1273% quote at {readerTime(f.series.at(-1)!.timestamp)} remains; the separately appended 100% settlement endpoint at the same minute is excluded. The final match result is independent of the selected probability. Event {f.eventID}.</p><section><h3>Original timestamps</h3><p>Pre-match snapshot: {tennisPropEvidence.headline.at}. Verified start: {tennisPropEvidence.start}. Score capture: {f.scoreAt}. Last genuine quote: {f.series.at(-1)!.timestamp}.</p></section></section>
 </div>}
export function TennisFinalHero({wide=false,large=false}:{wide?:boolean;large?:boolean}){
 const [index,setIndex]=useStoryState('tennis-final','historyObservation',f.series.length-1);
 const history=f.series.map(p=>({t:Date.parse(p.timestamp),h:p.home_probability,a:1-p.home_probability}));
 const series=history.flatMap((p,i)=>i&&p.t-history[i-1].t>300000?[{t:p.t-1,h:null,a:null},p]:[p]);
 const at=history[index],datedAxis=readerCrossesDay(history);
 return <section className="specialized-headline panel tennis-final-headline">
 <div className="tennis-headline-summary">
  <div className="hero-head"><span>ATP · SHANGHAI · FINAL</span><HeadlineInfo scopeKey="tennis:15327291:final" wide={wide} large={large}><TennisFinalHeadlineFacts/></HeadlineInfo></div>
  <h1 className="sr-only">{f.home} · {f.away}</h1>
  <div className="specialized-contenders">{[[f.home,f.prematchHome],[f.away,f.prematchAway]].map(([name,chance],i)=><div key={String(name)} className={i?'away':'home'}><span>{name}</span><small>Pre-match chance · Kalshi</small><strong>{pct(Number(chance))}</strong></div>)}</div>
  <div className="tennis-final-actual"><strong>{f.homeSets}–{f.awaySets}<small>sets</small></strong><div><b>Final · Fokina won</b><span>Games {f.homeGames}–{f.awayGames}</span></div></div>
 </div>
 <section className="tennis-journey" aria-label="Fokina and Tiafoe recorded probability journey">
  <div className="tennis-journey-heading"><h3>The probability journey</h3></div>
  <div className="tennis-journey-plot" role="img" aria-label="171 recorded Fokina and Tiafoe win probabilities on a zero to 100% scale. Gaps stay blank. Final result is separate from probabilities."><ResponsiveContainer width="100%" height="100%"><LineChart data={series} margin={{left:-12,right:28,top:16,bottom:12}}><CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 4"/><XAxis dataKey="t" type="number" domain={['dataMin','dataMax']} tickFormatter={t=>readerClock(t)} tick={datedAxis?(d:any)=><text x={d.x} y={d.y+12} textAnchor="middle" fill="var(--text-secondary)" fontSize={11}><tspan x={d.x}>{readerTime(d.payload.value,{dateOnly:true})}</tspan><tspan x={d.x} dy={13}>{readerClock(d.payload.value)}</tspan></text>:{fontSize:11}} tickCount={3} minTickGap={45} height={datedAxis?42:30} axisLine={false} tickLine={false}/><YAxis domain={[0,1]} ticks={[0,.5,1]} tickFormatter={pct} tick={{fontSize:11}} axisLine={false} tickLine={false}/><Line name="Fokina" dataKey="h" stroke="var(--series-home)" strokeWidth={2.5} dot={false} connectNulls={false} isAnimationActive={false}/><Line name="Tiafoe" dataKey="a" stroke="var(--series-away)" strokeWidth={2.5} dot={false} connectNulls={false} isAnimationActive={false}/><ReferenceLine x={at.t} stroke="var(--text-secondary)" strokeDasharray="3 3"/>{(['h','a'] as const).map((side,i)=><ReferenceDot key={side} x={at.t} y={at[side]} r={4} stroke={`var(--series-${i?'away':'home'})`} strokeWidth={2} fill={`var(--series-${i?'away':'home'})`}/>)}</LineChart></ResponsiveContainer></div>
  <div className="tennis-history-readout" aria-live="polite"><span>● Recorded in match · {readerTime(at.t)}</span><div><strong className="home">Fokina {pct(at.h)}</strong><strong className="away">Tiafoe {pct(at.a)}</strong></div></div>
  <div className="tennis-history-inspect"><button aria-label="Previous Fokina–Tiafoe observation" disabled={index===0} onClick={()=>setIndex(index-1)}>‹</button><input {...rangeGestureProps} type="range" aria-label="Tennis historical observation" aria-valuetext={`${readerTime(at.t)}; Fokina ${pct(at.h)}, Tiafoe ${pct(at.a)}`} min={0} max={history.length-1} value={index} onChange={e=>setIndex(+e.target.value)}/><button aria-label="Next Fokina–Tiafoe observation" disabled={index===history.length-1} onClick={()=>setIndex(index+1)}>›</button></div>
 </section>
 </section>
}

function TennisFinalStory({kind,total,setTotal,scoreKey,setScoreKey,onPick}:{kind:TennisFinalKind;total:number;setTotal:Dispatch<SetStateAction<number>>;scoreKey:string;setScoreKey:Dispatch<SetStateAction<string>>;onPick:(r:Row)=>void}){
 const totalRow=group(f.bindings.totals[total])[0];
 const exact=group(f.bindings.exactScore);
 const stories={
sets:<article className="atlas-card tennis-card"><span className="eyebrow">SET WINNERS · FINAL</span><h3>Two tight sets decided it</h3><p className="tennis-subtitle">Fokina won the match. Games finished level, 18–18.</p><div className="tennis-set-path">{f.sets.map((set,i)=><div key={i} className="tennis-set"><span className="eyebrow">Set {i+1}</span><strong>{set[0]}<span>–</span>{set[1]}</strong>{f.bindings.setWinner[i]&&<div className="tennis-set-baselines">{names.map(name=>{const row=group(f.bindings.setWinner[i]!).find(r=>r.outcome_name.includes(name));return <div key={name}><span>{name} to win set</span><TennisPropChance row={row} rail/></div>})}</div>}{set.map((n,j)=><div key={j} className={'tennis-games '+(j?'away':'home')} aria-label={`${names[j]} ${n} games`}><span>{names[j]}</span><div>{Array.from({length:7},(_,k)=><i key={k} className={k<n?'filled':''}/>)}</div></div>)}{f.bindings.setWinner[i]?<button className="card-link" onClick={()=>onPick(group(f.bindings.setWinner[i]!).find(r=>r.is_winner)!) }>{set[0]>set[1]?'Fokina':'Tiafoe'} won <ChevronRightIcon/></button>:<span className="tennis-no-contract">Fokina won · score only<br/>No set-3 prop supplied</span>}</div>)}</div><p className="atlas-note">Each block = one game won, not point-by-point order. Set 1 and 2 buttons open the settled winner contracts. Pre-match set chances: Polymarket, {readerTime(tennisPropBaseline(group(f.bindings.setWinner[0]!)[0])!.at)}.</p></article>,
totals:<article className="atlas-card tennis-card"><span className="eyebrow">TOTAL GAMES · ACTUAL VS OPENING LINE</span><h3>A longer match than the line</h3><PregameContext label="Pre-match chance" value={tennisPropBaseline(totalRow)?.value} subject={`Over ${String(totalRow.threshold)} games`} note={tennisPropNote(totalRow)}/><div className="tennis-delta"><strong>36<span>games</span></strong><b>+13.5<small>above opening line</small></b></div><div className="tennis-total-plot" role="img" aria-label="Opening total line 22.5 games; actual 36 games. The line is a market threshold, not an expected mean."><svg viewBox="0 0 320 105"><line x1="12" x2="308" y1="48" y2="48" className="axis"/><line x1={12+22.5/40*296} x2={12+36/40*296} y1="48" y2="48" className="distance"/><circle cx={12+22.5/40*296} cy="48" r="6" className="opening"/><line x1={12+36/40*296} x2={12+36/40*296} y1="30" y2="64" className="actual"/><text x={12+22.5/40*296} y="22" textAnchor="middle">22.5 opening</text><text x={12+36/40*296} y="80" textAnchor="middle">36 actual</text>{[0,10,20,30,40].map(n=><text key={n} x={12+n/40*296} y="101" textAnchor="middle" className="tick">{n}</text>)}</svg></div><p className="atlas-note">○ Opening market line · │ Actual games<br/>A threshold, not a projected score or expected average. Opening time unavailable.</p><div className="tennis-total-options" aria-label="Settled game totals">{f.bindings.totals.map((id,i)=><button key={id} aria-pressed={total===i} onClick={()=>setTotal(i)}><strong>Over {String(group(id)[0].threshold)}</strong><TennisPropChance row={group(id)[0]}/><span>Won ✓</span></button>)}</div><button className="card-link" onClick={()=>onPick(totalRow)}>Original {String(totalRow.threshold)}-game contract <ChevronRightIcon/></button></article>,
exact:<article className="atlas-card tennis-card"><span className="eyebrow">EXACT MATCH SCORE · SETS</span><h3>Which finish happened?</h3><TennisScoreStory rows={exact} onPick={onPick} selectedKey={scoreKey} onSelection={setScoreKey}/><details className="tennis-handicaps"><summary>Set handicaps ≠ game handicaps</summary><p>Fokina won one more set; total games were tied. These are different units.</p>{[...f.bindings.setHandicaps,f.bindings.gameHandicap].map(id=><button key={id} onClick={()=>onPick(group(id)[0])}>{group(id)[0].market_name}<ChevronRightIcon/></button>)}</details></article>,
 handicaps:<TennisHandicapStory onPick={onPick}/>
 };
 return stories[kind];
}
export function TennisFinalStories({onPick,wide,large}:{onPick:(r:Row)=>void;wide:boolean;large:boolean}){
 const keyboard=useKeyboard(),memory=useStoryReaderMemory('tennis-final');
 const [total,setTotal]=useStoryState('tennis-final','total',1);
 const [scoreKey,setScoreKey]=useStoryState('tennis-final','exactScore',group(f.bindings.exactScore)[0].key);
 const [readerActive,setReaderActive]=useStoryState<string|null>('tennis-final','readerActive',null);
 const [focus,setFocus]=useStoryState<TennisFinalKind|null>('tennis-final','focus',null);
 const story=(kind:TennisFinalKind)=><TennisFinalStory kind={kind} total={total} setTotal={setTotal} scoreKey={scoreKey} setScoreKey={setScoreKey} onPick={onPick}/>;
 return <><StoryStream event="tennis-final" subject="match" wide={wide} readerOpen={focus!==null} cards={tennisFinalCards.map(card=>({...card,visual:<div className="tennis-final-story-slot"><ExpandCard label={card.name} onClick={()=>{keyboard.hide();setReaderActive(card.id);setFocus(card.id)}}/>{story(card.id)}</div>}))}/>
 <CardFocus memory={memory} resumeAt={readerActive} onActiveCardChange={setReaderActive} start={focus} cards={tennisFinalCards.map(card=>({...card,visual:<div className={`tennis-final-focus ${large?'large-text':''}`}>{story(card.id)}</div>}))} wide={wide} large={large} onClose={()=>setFocus(null)} returnLabel="Back to match" anchor={<><b>Fokina 2–1 Tiafoe · Final · sets</b><span>Pre-match · Fokina {pct(f.prematchHome)} / Tiafoe {pct(f.prematchAway)}</span></>}/>
 </>;
}
