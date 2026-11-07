import {readerTime} from './readerTime';
import {reportedEsportsFinal} from './esportsFinalScore';
import {EsportsFinalScore,EsportsFinalFacts} from './EsportsFinalResultView';
import {HeadlineInfo} from './HeadlineInfo';
import {EsportsWinnerJourney} from './EsportsWinnerJourney';
import {retainedEsportsWinnerHistory} from './esportsWinnerHistory';
import {probabilityLabel as pct} from './probabilityLabel';
import './specializedHeadlines.css';
import './esportsHistoryReader.css';
const clock=(at:string)=>readerTime(at);
export function EsportsHeadlineFacts(){const baseline=retainedEsportsWinnerHistory.filter(p=>p.pregame).at(-1)!;return <div className="capture-headline-facts">
 <section><h3>Pre-match expectation</h3><p>Nice Try {pct(baseline.home)}; Flame Hard {pct(baseline.away)}. Last retained observation before the verified start: {clock(baseline.at)}.</p><details><summary>Original timestamp</summary><code>{baseline.at}</code></details></section>
 {reportedEsportsFinal?<EsportsFinalFacts/>:<section><h3>Current state</h3><p>Suspended. Current winner probabilities are unconfirmed. The terminal settlement marker and provider prop results do not establish a confirmed match result, map score or finish time.</p></section>}
 <section><h3>History and source</h3><p>{retainedEsportsWinnerHistory.length.toLocaleString()} retained Bain Luck blend observations. Flame Hard is the complement of the supplied Nice Try aggregate for this verified two-team market, not an independent provider quote.</p><p>Dates and times are local to your device. Gaps over five minutes stay blank. Around start includes the last pre-match observation. After-start probabilities do not establish a map or round, finish time or final result. The terminal settlement marker and all probabilities at or after it are excluded.</p><p>Event 15322123 · esports-event-history.json. Original request time is unavailable. No score or projection is inferred.</p></section>
 </div>}
export function EsportsHeadline({wide,large}:{wide:boolean;large:boolean}){const baseline=retainedEsportsWinnerHistory.filter(p=>p.pregame).at(-1);return <section className="specialized-headline panel combat-headline esports-headline">
 <div className="hero-head"><span>CS2 · {reportedEsportsFinal?'FINAL':'SUSPENDED'}</span><HeadlineInfo scopeKey="esports:15322123" wide={wide} large={large}><EsportsHeadlineFacts/></HeadlineInfo></div>
 <h1 className="sr-only">Nice Try · Flame Hard</h1>
 <div className="specialized-contenders">{[['Nice Try',baseline?.home],['Flame Hard',baseline?.away]].map(([name,chance],i)=><div key={String(name)} className={i?'away':'home'}><span>{name}</span><small>Last pre-match chance</small><strong>{typeof chance==='number'?pct(chance):'Unavailable'}</strong></div>)}</div>
 {reportedEsportsFinal?<EsportsFinalScore/>:<p className="specialized-state">Current probability unavailable · match result unconfirmed</p>}
 <EsportsWinnerJourney compact wide={wide} large={large}/>
 </section>}
