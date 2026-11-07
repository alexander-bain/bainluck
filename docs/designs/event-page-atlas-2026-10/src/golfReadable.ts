import {journeyFor,windowPoints,type JourneyWindow} from './golfJourneyEvidence.ts';
export function golfReadout(name:string,period:JourneyWindow,through?:string){
 const points=windowPoints(name,period,through),first=points[0]??null,last=points.at(-1)??null;
 const raw=journeyFor(name)?.baseline;
 const baseline=raw&&(!through||Date.parse(raw.timestamp)<=Date.parse(through))?raw:null;
 return {first,last,baseline,showBaseline:period!=='Pre',change:points.length>1?last!.probability-first!.probability:null};
}
export function beforeMovement(change:number|null){
 if(change===null)return 'One recorded estimate';
 if(change===0)return 'No change across recorded estimates';
 const amount=Math.abs(change)*100;
 return `${change>0?'↑':'↓'} ${amount<.1?'<0.1':amount.toFixed(1)} pts since first record`;
}

/** Sorted label rails preserve vertical order without changing the plotted probabilities. */
export function labelPositions(rows:{name:string;target:number}[],top:number,bottom:number,gap:number){
 const sorted=rows.slice().sort((a,b)=>a.target-b.target||a.name.localeCompare(b.name));
 const step=sorted.length>1?Math.min(gap,(bottom-top)/(sorted.length-1)):0;
 const positions:number[]=[];
 sorted.forEach((r,i)=>positions.push(Math.max(top,Math.min(bottom,r.target),i?positions[i-1]+step:top)));
 for(let i=positions.length-1;i>=0;i--)positions[i]=Math.min(positions[i],i===positions.length-1?bottom:positions[i+1]-step);
 return sorted.map((r,i)=>({...r,position:positions[i]}));
}
