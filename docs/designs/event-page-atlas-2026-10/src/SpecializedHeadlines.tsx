import {readerTime} from './readerTime';
import {officialCombatFinal} from './combatOfficialFinal';
import {CombatOfficialFacts} from './CombatOfficialResult';
import {HeadlineInfo} from './HeadlineInfo';
import {CombatWinnerJourney} from './CombatWinnerJourney';
import {retainedCombatWinnerHistory} from './combatWinnerHistory';
import {retainedSoccerHistory} from './soccerFinalHistory';
import {probabilityLabel as pct} from './probabilityLabel';
import soccer from './soccerPregameHeadline.json';
import soccerFinal from './soccerFinalHistory.json';
import './specializedHeadlines.css';

const clock=(at:string)=>readerTime(at);
export function CombatHeadlineFacts(){const baseline=retainedCombatWinnerHistory.filter(p=>p.pregame).at(-1)!;return <div className="capture-headline-facts">
 <section><h3>Pre-match expectation</h3><p>Gautier {pct(baseline.home)}; Kopylov {pct(baseline.away)}. Last retained observation before the verified start: {clock(baseline.at)}.</p><details><summary>Original timestamp</summary><code>{baseline.at}</code></details></section>
 {officialCombatFinal?<CombatOfficialFacts/>:<section><h3>Current state</h3><p>Suspended. Current winner probabilities are unconfirmed. Some provider props are resolved, but they do not establish a confirmed bout result, round or finish time.</p></section>}
 <section><h3>History and source</h3><p>{retainedCombatWinnerHistory.length.toLocaleString()} retained Bain Luck blend observations. Kopylov is the complement of the supplied Gautier aggregate for this verified two-fighter market, not an independent provider quote.</p><p>Dates and times are local to your device. Gaps over five minutes stay blank. Around start includes the last pre-match observation. After-start probabilities do not establish a round, finish time or final result. Unsupported terminal certainty values are excluded.</p><p>Event 15318681 · mma-event-history.json. Original request time is unavailable. No score or projection is inferred.</p></section>
 </div>}
export function CombatHeadline({wide,large}:{wide:boolean;large:boolean}){const baseline=retainedCombatWinnerHistory.filter(p=>p.pregame).at(-1);return <section className="specialized-headline panel combat-headline">
 <div className="hero-head"><span>COMBAT · {officialCombatFinal?'FINAL':'SUSPENDED'}</span><HeadlineInfo scopeKey="combat:15318681" wide={wide} large={large}><CombatHeadlineFacts/></HeadlineInfo></div>
 <h1 className="sr-only">Ateba Gautier · Roman Kopylov</h1>
 <div className="specialized-contenders">{[['Ateba Gautier',baseline?.home],['Roman Kopylov',baseline?.away]].map(([name,chance],i)=><div key={String(name)} className={i?'away':'home'}><span>{name}</span><small>Last pre-match chance</small><strong>{typeof chance==='number'?pct(chance):'Unavailable'}</strong></div>)}</div>
 {officialCombatFinal?<div className="specialized-state combat-official-finish" aria-label="Official final bout result"><strong>Kopylov won</strong><span>TKO · Round 1 · <b>3:12</b></span></div>:<p className="specialized-state">Current probability unavailable · bout result unconfirmed</p>}
 <CombatWinnerJourney compact wide={wide} large={large}/>
 </section>}
export function SoccerPregameFacts(){return <div className="capture-headline-facts"><section><h3>Pre-match quotes</h3>{soccer.rows.map(r=><p key={r.key}>{r.name==='Tie'?'Draw':r.name}: {pct(r.chance)} · {clock(r.at)}.</p>)}</section><section><h3>Source and coverage</h3><p>Three supplied Kalshi outcomes total 99.5%. Probabilities are independently timed and are not normalized. Draw is a supplied outcome, never a remainder. Complete blended three-way history is unavailable in this early capture.</p></section><section><h3>Match state</h3><p>Not started in this capture. Scheduled kickoff {clock(soccer.start)}. No actual score or valid score projection is available. Event {soccer.eventID}.</p></section></div>}
export function SoccerPregameHeadline({wide,large,mode}:{wide:boolean;large:boolean;mode:string}){return <section className="specialized-headline panel soccer-pregame-headline">
 <div className="hero-head"><span>SOCCER · PRE-MATCH</span><HeadlineInfo scopeKey="soccer:hull-everton:pregame" wide={wide} large={large}><SoccerPregameFacts/></HeadlineInfo></div>
 <h1 className="sr-only">Hull City · Everton</h1><p className="specialized-context">Pre-match chances · Kalshi only</p>
 <div className="specialized-contenders three">{soccer.rows.map((r,i)=><div key={r.key} className={i===0?'home':i===2?'away':'draw'}><span>{r.name==='Tie'?'Draw':r.name}</span><strong className={mode==='captured'?'':'specialized-missing'}>{mode==='captured'?pct(r.chance):'Current probability unavailable'}</strong>{mode!=='captured'&&<small>Captured pre-match {pct(r.chance)}</small>}</div>)}</div>
 <div className="specialized-kickoff"><strong>Not started</strong><span>{clock(soccer.start)}</span></div><p className="specialized-state">Blended history unavailable</p>
 </section>}
export function SoccerFinalFacts(){const baseline=retainedSoccerHistory.filter(p=>p.pregame).at(-1)!;return <div className="capture-headline-facts"><section><h3>Last pre-match chances</h3><p>Hull {pct(baseline.home)}; Draw {pct(baseline.draw)}; Everton {pct(baseline.away)}. Observed {clock(baseline.at)}.</p><details><summary>Original timestamp</summary><code>{baseline.at}</code></details></section><section><h3>Final score</h3><p>2–2 · Draw. Supplied by event detail and game markets, captured {clock(soccerFinal.scoreObservedAt)}. The final score stays separate from the inspected quote.</p></section><section><h3>History and source</h3><p>{retainedSoccerHistory.length.toLocaleString()} retained three-way Kalshi observations. The supplied probabilities are not normalized; draw is not computed as a remainder. Complete blended history is unavailable.</p><p>Rows at or after completion, terminal rows and incomplete triples are excluded. Dates and times are local to your device. Gaps over five minutes stay blank. Props retain their independently reported results, including earlier props missing from the final capture. Event {soccerFinal.eventID}.</p></section></div>}
