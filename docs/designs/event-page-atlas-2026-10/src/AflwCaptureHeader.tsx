import {readerTime} from './readerTime';
import {aflwStart} from './aflwWinnerHistory';
import {AflwWinnerJourney} from './AflwWinnerJourney';
import {aflwHistoryStage} from './aflwHistoryStage';
import './aflwCaptureHistory.css';
import {aflwCaptures} from './aflwCaptureEvidence';
import {probabilityLabel} from './probabilityLabel';
import type {CatalogEvidenceRow} from './probabilityPresentation';
import {aflwHeadlineSides} from './aflwHeadlineEvidence';
const time=(value:string)=>readerTime(value,{seconds:true});
export function AflwCaptureHeader({status,rows,mode,wide,large}:{status:string;rows:CatalogEvidenceRow[];mode:string;wide:boolean;large:boolean}){
 const latest=status==='suspended';const stage=latest?'suspended':'earlier';const history=aflwHistoryStage(stage);const sides=aflwHeadlineSides(rows,status,mode);
 const clocks=sides.flatMap(side=>side.quote?[time(side.quote.observedAt)]:[]);const sharedClock=clocks.length===2&&new Set(clocks).size===1?clocks[0]:null;
 return <section className="atlas-hero panel retained-hero aflw-capture-history"><div className="aflw-capture-summary">
  <div className="hero-head"><span>AFL Women's · {latest?'Suspended':'Earlier in-game capture'}</span></div>
  <h1>Sydney Swans · Carlton Blues</h1>
  <div className="retained-title"><h2>Chance to win</h2><span className="retained-phase">{sides.some(side=>side.quote)?'Recorded quote':'Probability unavailable'}</span></div>
  <div className="retained-win-pair">{sides.map(side=><div key={side.id}>
   <span>{side.name}</span><strong className={side.quote?'':'retained-unavailable'}>{side.quote?probabilityLabel(side.quote.value):mode==='loading'?'Loading…':'Current probability unavailable'}</strong>
   <span className="retained-baseline">Pregame quote {probabilityLabel(side.id===242153909?history.baseline?.home:history.baseline?.away)}</span>
   {side.quote&&!sharedClock&&<small>Recorded {time(side.quote.observedAt)}</small>}
  </div>)}</div>
  {sharedClock&&<p className="retained-shared-clock">Recorded {sharedClock}</p>}
  <p className="retained-state">Score and quarter unavailable.{latest&&' Match result unconfirmed.'}</p>
  <details className="retained-capture-evidence"><summary><span aria-hidden="true">ⓘ</span> About these probabilities</summary>
   <p>The event history supplies Sydney 32% / Carlton 68% at {history.baseline?time(history.baseline.at):'an unavailable time'}, before confirmed kickoff at {readerTime(aflwStart)}. The earlier 37% / 63% prop snapshot has its own later quote timestamps. Neither source proves an actively traded current probability. Event history does not establish each original contract’s baseline.</p>
   <p>Polymarket source capture: {time(latest?aflwCaptures.latestAt:aflwCaptures.earlierAt)}. The team readouts retain their own quote timestamps. History was captured separately later, then limited to observations at or before this capture time; this is not proof of what had reached the app then. Projected final unavailable.</p><p>Original capture timestamp: {latest?aflwCaptures.latestAt:aflwCaptures.earlierAt}. Original quote timestamps: {sides.flatMap(side=>side.quote?[side.quote.observedAt]:[]).join('; ')||'unavailable'}.</p>
   {latest&&<><p>Provider event note: “{aflwCaptures.latestDetail.venue_settled_result}”.</p><p>The supplied status is suspended and no score was supplied. This event-level note does not independently confirm the match result or grade its original props.</p></>}
  </details></div><AflwWinnerJourney stage={stage} showBaseline={false} wide={wide} large={large}/>
 </section>;
}
