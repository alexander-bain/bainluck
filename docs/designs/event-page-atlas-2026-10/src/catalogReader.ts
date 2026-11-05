/** A reader only mounts the catalog's loaded cards. It never relabels this
 * bounded set as the complete event or changes source grouping. */
export function catalogReaderDeck<T extends {key:string}>(groups:T[],limit:number){
 const count=Number.isFinite(limit)?Math.max(1,Math.floor(limit)):12;
 return groups.slice(0,count);
}
export function catalogReaderStart<T extends {key:string}>(deck:T[],key:string|null){return key!==null&&deck.some(g=>g.key===key)?key:null}

import {totalExpectation,totalPregameRecord} from './totalPregame.ts';
/** Admit the already-verified Clippers–Warriors total chart only for its
 * complete, unfiltered final specimen. Unknown totals retain original cards. */
export function catalogTotalExpectationEligible(eventID:unknown,status:string,rows:unknown[],visibleRows:unknown[],absent=false){
 if(eventID!==15320337||status!=='completed'||absent||rows.length!==totalExpectation.records.length||visibleRows.length!==rows.length)return false;
 const records=rows.map(totalPregameRecord);
 return records.every(Boolean)&&new Set(records.map(r=>r!.key)).size===totalExpectation.records.length;
}
