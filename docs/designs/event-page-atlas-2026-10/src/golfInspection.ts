import {tournamentTimeline,windowPoints,type JourneyWindow} from './golfJourneyEvidence.ts';
export type GolfInspection={kind:'point';at:string}|{kind:'gap'}|null;
export function inspectionTimes(names:string[],period:JourneyWindow,through?:string){return [...new Set(names.flatMap(n=>windowPoints(n,period,through).map(p=>p.timestamp)))].sort((a,b)=>Date.parse(a)-Date.parse(b)||a.localeCompare(b))}
export function exactObservation(name:string,period:JourneyWindow,at:string,through?:string){const points=windowPoints(name,period,through).filter(p=>p.timestamp===at);return points.length===1?points[0]:null}
export function inspectFraction(names:string[],period:JourneyWindow,fraction:number,through?:string):GolfInspection {
 if(!Number.isFinite(fraction)||fraction<0||fraction>1)return null;
 const map=tournamentTimeline(period,through),times=inspectionTimes(names,period,through);if(!times.length)return null;
 if(map.gaps.some(g=>fraction>map.fraction(g.start)&&fraction<map.fraction(g.end)))return {kind:'gap'};
 // A shared field clock must not make a blank selected-golfer interval selectable.
 const first=Date.parse(times[0]),last=Date.parse(times.at(-1)!);
 if(fraction<map.fraction(first)||fraction>map.fraction(last))return {kind:'gap'};
 for(let i=1;i<times.length;i++){
  const before=Date.parse(times[i-1]),after=Date.parse(times[i]);
  if(after-before>30*60*1000&&fraction>map.fraction(before)&&fraction<map.fraction(after))return {kind:'gap'};
 }
 let at=times[0],distance=Infinity;for(const t of times){const d=Math.abs(map.fraction(Date.parse(t))-fraction);if(d<distance){distance=d;at=t}}return {kind:'point',at};
}
