import type {CSSProperties} from 'react';
import {cricketChanceChange} from './cricketMomentStories';
import {liveCricketSides,cricketLiveName,liveCricketBaseline} from './cricketLiveEvidence';
import {probabilityLabel as pct} from './probabilityLabel';
import './cricketMomentStream.css';
const colors={SA:'var(--series-home)',AUS:'var(--series-away)',TIE:'var(--text-secondary)'};
export function CricketChanceShift({stage,mode}:{stage:number;mode:string}){
 return <article className="atlas-card cricket-chance-shifts"><span className="eyebrow">Pregame → recorded chance</span><h3>How the outlook changed</h3><p className="cricket-shift-key">Hollow = pregame · solid = recorded</p><div className="cricket-shift-scale"><span>0%</span><span>Chance</span><span>100%</span></div>{liveCricketSides.map(side=>{
  const b=liveCricketBaseline(side),change=cricketChanceChange(side,stage,mode);
  return <div key={side} className="cricket-chance-shift" style={{'--chance-ink':colors[side]} as CSSProperties}>
   <div className="cricket-shift-name"><b>{cricketLiveName(side)}</b><strong>{change?`${change.delta>=0?'+':''}${(change.delta*100).toFixed(1)} pts`:'Current probability unavailable'}</strong></div>
   <div className="cricket-shift-track" role="img" aria-label={`${cricketLiveName(side)}: pregame ${pct(b?.value)}; recorded ${change?pct(change.quote.value):'Current probability unavailable'}. Changes are percentage points.`}>
    {b&&<i style={{left:`${b.value*100}%`}}/>}{change&&<><span style={{left:`${Math.min(change.baseline.value,change.quote.value)*100}%`,width:`${Math.abs(change.delta)*100}%`}}/><b style={{left:`${change.quote.value*100}%`}}/></>}
   </div><div className="cricket-shift-values"><span>Pregame <b>{pct(b?.value)}</b></span>{change&&<span>Recorded <b>{pct(change.quote.value)}</b></span>}</div>
  </div>
 })}<p className="cricket-live-note">Changes are percentage points, not runs or wickets.</p></article>
}
