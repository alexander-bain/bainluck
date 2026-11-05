import {SingleOutcomeVisual} from './SingleOutcomeVisual';
import {ChevronRightIcon} from '@radix-ui/react-icons';
import {probabilityLabel} from './probabilityLabel';
import {nflOriginalBaseline,type NFLOriginalRow} from './nflOriginalBaseline';
import './nflOriginalPregame.css';
export function NFLOriginalPregame({row}:{row:NFLOriginalRow}){
 const baseline=nflOriginalBaseline(row);
 return <section className="nfl-original-pregame" aria-label="Selected original pregame probability">
  <SingleOutcomeVisual row={{...row,key:row.row_key}} state={{kind:'unavailable',label:'Current probability unavailable',value:null,observedAt:null}}/>
  <details><summary><ChevronRightIcon/>About this pregame chance</summary><p>{baseline.note}</p>
   {baseline.basis==='inverted-own-row'&&<p>The selected outcome uses one minus the normalized baseline in this outcome’s own record ({probabilityLabel(baseline.raw)}). It does not borrow the opposite outcome’s baseline.</p>}
   {baseline.basis==='direct-own-row'&&<p>This is the normalized baseline supplied in this selected outcome’s own record.</p>}
   <p>Separate outcome records retain their own baselines; this view does not force them to add to 100%.</p>
  </details>
 </section>;
}
