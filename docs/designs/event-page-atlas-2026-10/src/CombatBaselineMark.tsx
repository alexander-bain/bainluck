import {combatPregame,combatQuoteTime} from './combatPregame';
import {probabilityLabel} from './probabilityLabel';
import type {CombatRow} from './combatOutcome';
export function CombatBaselineMark({row,compact=false,sideLabel,showClock=true,style='ring'}:{row:CombatRow;compact?:boolean;sideLabel?:string;showClock?:boolean;style?:'ring'|'rail'}){
 const p=combatPregame(row);
 return <span className="combat-baseline-mark">{p?<>
  {style==='rail'?<><strong>{probabilityLabel(p.value)}</strong><span className="combat-probability-rail" aria-hidden="true"><span style={{left:`${p.value*100}%`}}/></span></>:compact?<strong>○ {probabilityLabel(p.value)}</strong>:<span className="combat-chance-ring"><svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="27" className="ring-track"/><circle cx="32" cy="32" r="27" className="ring-chance" pathLength="1" strokeDasharray={`${p.value} 1`} transform="rotate(-90 32 32)"/></svg><strong>{probabilityLabel(p.value)}</strong></span>}
  <span>{sideLabel?`${sideLabel} · pre-match`:"Pre-match"}</span>{showClock&&<small>{combatQuoteTime(p.at)}</small>}
 </>:<span>{sideLabel?`${sideLabel} · pre-match unavailable`:"Pre-match unavailable"}</span>}</span>
}
