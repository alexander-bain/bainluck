import {golferNames,recordedHistory} from './golfOutlookEvidence.ts';
export type OutlookScale='auto'|'full';
/** One captured field sets the clock and scale; choosing a golfer cannot move either. */
export function outlookHistoryFrame(name:string,scale:OutlookScale='auto'){
 const all=golferNames.flatMap(recordedHistory);
 const points=recordedHistory(name).slice().sort((a,b)=>Date.parse(a.timestamp)-Date.parse(b.timestamp));
 const clocks=all.map(p=>Date.parse(p.timestamp));
 const domain:readonly[number,number]|null=clocks.length?[Math.min(...clocks),Math.max(...clocks)]:null;
 const maximum=Math.max(0,...all.map(p=>p.probability));
 const caps=[.01,.02,.03,.05,.1,.15,.2,.25,.3,.5,.75,1];
 const cap=scale==='full'?1:caps.find(v=>v>=Math.min(1,maximum*1.1))??1;
 return {points,domain,cap,capturedGolfers:golferNames.filter(n=>recordedHistory(n).length>0).length};
}
