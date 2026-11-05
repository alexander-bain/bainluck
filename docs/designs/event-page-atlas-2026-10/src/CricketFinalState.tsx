import {readerTime} from './readerTime';
import {cricketFinal} from './cricketFinalScore';
import {probabilityLabel} from './probabilityLabel';
import {cricketSeries,cricketEvent,type CricketPoint} from './cricketEvidence';

export function CricketFinalSummary(){
 const w=cricketFinal;if(!w)return <p>Final score unavailable.</p>;
 return <section className="ck-final-summary" aria-label="Final match score"><b>Final · Match drawn</b><div>{[w.home,w.away].map(team=><div key={team}><span>{team}</span><strong>{w.innings.filter(i=>i.team===team).map(i=>i.originalScore).join(' & ')}</strong></div>)}</div><small>1st &amp; 2nd innings · d = declared</small></section>;
}
/** Compact actuals in the headline; these never change with history inspection. */
export function CricketHeadlineScore(){
 const w=cricketFinal;if(!w)return <p>Final score unavailable.</p>;
 return <dl className="ck-headline-scores" aria-label="Final innings scores">{[w.home,w.away].map(team=><div key={team}><dt>{team}</dt><dd aria-label={w.innings.filter(i=>i.team===team).map(i=>i.originalScore.replace(/ d$/,' declared')).join(' and ')}>{w.innings.filter(i=>i.team===team).map(i=>i.originalScore).join(' & ')}</dd></div>)}</dl>;
}
export function CricketFinalChase({point,onExpand,timeZone}:{point:CricketPoint|null;onExpand?:()=>void;timeZone?:string}){
 const w=cricketFinal;if(!w)return null;const c=w.chase,contract=cricketSeries().find(s=>s.ticker===cricketEvent+'-TIE'),result=contract?.result==='yes'?'Won':contract?.result==='no'?'Lost':'Unconfirmed';
 return <section className="ck-card ck-chase" aria-label="Final chase and recorded draw or tie chance"><header><div><span className="ck-eyebrow">DRAW / TIE CONTRACT · {result}</span><h2>A draw, with one wicket left</h2></div>{onExpand&&<button aria-label="Expand final cricket chase" onClick={onExpand}>↗</button>}</header><div className="ck-chase-price"><div><span>Recorded draw / tie chance</span><strong>{point?probabilityLabel(point.p):'Not traded'}</strong></div><span>{point?readerTime(point.at*1000,{timeZone}):'No trade at this inspected hour'}<br/>Pre-match chance unavailable</span></div><div className="ck-chase-final"><span>FINAL · INDIA A’S SECOND INNINGS</span><div className="ck-chase-score"><strong>{c.runs}<small> runs</small></strong><span>{c.overs.replace(/\.0$/,'')} overs</span></div><div className="ck-run-target" role="img" aria-label={`${c.runs} final runs against a target of ${c.targetRuns} runs to win. Match drawn, not a loss.`}><div style={{width:`${c.runs/c.targetRuns*100}%`}}/><span className="ck-target-rule"/></div><div className="ck-run-labels"><span>0 runs</span><b>Target {c.targetRuns}</b></div><div className="ck-wickets" role="img" aria-label={`${c.wicketsLost} wickets lost, ${10-c.wicketsLost} wicket left`}>{Array.from({length:10},(_,i)=><span key={i} className={i<c.wicketsLost?'used':''}/>)}</div><div className="ck-wicket-labels"><b>{c.wicketsLost} wickets lost</b><span>{10-c.wicketsLost} left</span></div><p>India A finished short of the win target and kept their last wicket. The match was drawn.</p></div><p className="ck-note">Final score stays fixed while you inspect earlier probabilities. Draw and tie are separate sporting results; this contract combines them.</p></section>;
}
