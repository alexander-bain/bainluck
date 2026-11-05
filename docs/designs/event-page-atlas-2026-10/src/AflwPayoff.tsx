import {useState} from 'react';
import {ArrowTopRightIcon} from '@radix-ui/react-icons';
import {CardFocus} from './CardFocus';
import {useStoryState,useStoryReaderMemory} from './StorySession';
import {AflwWinnerJourney} from './AflwWinnerJourney';
import {aflwPayoff} from './aflwPayoffEvidence';
import {probabilityLabel as pct} from './probabilityLabel';
import {readerTime} from './readerTime';
import './aflwPayoff.css';
export function AflwPayoff({detail,wide,large}:{detail:Record<string,unknown>;wide:boolean;large:boolean}){
 const story=aflwPayoff(detail),[open,setOpen]=useState(false),[selected,setSelected]=useStoryState('aflw:final:payoff','quarter',3),memory=useStoryReaderMemory('aflw:final:payoff');
 if(!story)return null;
 const {baseline,actual,breaks}=story,q=breaks.find(x=>x.id===selected)??breaks[3];
 const content=(expanded=false)=><section className={`aflw-payoff ${expanded?'aflw-payoff-expanded':''} ${large?'aflw-payoff-large':''} ${wide?'aflw-payoff-wide':''}`} aria-label="AFLW pregame expectation and official result">
  <header><div><span className="aflw-payoff-eyebrow">PREGAME EXPECTATION · ACTUAL RESULT</span><h2>{story.title}</h2></div>{!expanded&&<button aria-label="Expand AFLW expectation and result" onClick={()=>setOpen(true)}><ArrowTopRightIcon/></button>}</header>
  <div className="aflw-payoff-expectation"><h3>Before the match</h3><div className="aflw-payoff-chances">{[{name:'Sydney',p:baseline?.home,side:'home'},{name:'Carlton',p:baseline?.away,side:'away'}].map(row=><div className={`aflw-payoff-${row.side}`} key={row.side}><span>{row.name}</span><b>{row.p===undefined?'Unavailable':pct(row.p)}</b><div className="aflw-payoff-prob-track" role="img" aria-label={`${row.name} pregame win chance ${row.p===undefined?'unavailable':pct(row.p)}`}><i style={{width:row.p===undefined?0:`${row.p*100}%`}}/></div></div>)}</div><p>Event win chance · {baseline?readerTime(baseline.at,{seconds:true}):'No qualified pregame quote'}</p></div>
  <div className="aflw-payoff-result"><span>OFFICIAL FINAL</span><strong>Carlton <b>59–32</b> Sydney</strong><p>Won by 27 points</p></div>
  <div className="aflw-payoff-breaks"><h3>Carlton’s lead at each break</h3><p>Actual points ahead · starts at zero</p><div className="aflw-payoff-bars" role="group" aria-label="Inspect an AFLW quarter break">{breaks.map(b=><button key={b.id} aria-pressed={selected===b.id} aria-label={`${b.label}: Carlton ahead by ${b.lead} points, score ${b.away} to ${b.home}`} onClick={()=>setSelected(b.id)}><span className="aflw-payoff-bar-area"><b>{b.lead}</b><i style={{height:`${b.lead/30*96}px`}}/></span><span>{b.label}</span></button>)}</div><div className="aflw-payoff-break-readout" aria-live="polite"><b>{q.label} · Carlton {q.away}–{q.home} Sydney</b><span>{q.gain} points added to the lead in {q.id===3?'Q4':`Q${q.id+1}`}</span></div></div>
  <p className="aflw-payoff-takeaway">An 18-point first-quarter lead became 27 at the final.</p>
  <details><summary>Probability and score sources</summary><p>The pregame numbers are independently supplied Polymarket event quotes, not individual-prop baselines or a current probability. They describe who would win, not the expected margin.</p><p>Official AFL quarter scores supply the actual points. Quarter-end timestamps are unavailable, so these marks are not aligned to the probability-history clock. Original contract settlement remains unconfirmed.</p><a href={actual.source.url} target="_blank" rel="noreferrer">Official match report ↗</a></details>
 </section>;
 return <>{content()}<CardFocus memory={memory} start={open?'payoff':null} cards={[{id:'payoff',name:'Expectation & result',visual:content(true)},{id:'history',name:'Win probability history',visual:<AflwWinnerJourney stage="final" expanded wide={wide} large={large}/>}]} wide={wide} large={large} onClose={()=>setOpen(false)} readerTitle="AFLW match stories" returnLabel="Back to match" anchor={<><b className="aflw-payoff-reader">Sydney 32–59 Carlton · Final</b><span>Pregame win chance · Sydney {pct(baseline?.home)} / Carlton {pct(baseline?.away)}</span></>}/></>;
}
