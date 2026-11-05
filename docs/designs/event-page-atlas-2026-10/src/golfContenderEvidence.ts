import {journeyNames,journeyFor,windowPoints} from './golfJourneyEvidence.ts';

/** One exact captured instant. Never carry forward a quote or normalize this sample. */
export function beforeContenders(through:string,at?:string){
 if(!Number.isFinite(Date.parse(through))||(at!==undefined&&(!Number.isFinite(Date.parse(at))||Date.parse(at)>Date.parse(through))))return null;
 const captured=journeyNames.map(name=>({name,id:journeyFor(name)!.original.id,points:windowPoints(name,'Pre',through)}));
 const timestamp=at??captured.flatMap(r=>r.points.map(p=>p.timestamp)).sort((a,b)=>Date.parse(a)-Date.parse(b)).at(-1);
 if(!timestamp)return null;
 const rows=captured.flatMap(r=>{const matches=r.points.filter(p=>p.timestamp===timestamp);const p=matches[0];return matches.length===1&&p&&Number.isFinite(p.probability)&&p.probability>=0&&p.probability<=1?[{name:r.name,id:r.id,probability:p.probability,timestamp}]:[];}).sort((a,b)=>b.probability-a.probability||a.name.localeCompare(b.name));
 if(!rows.length)return null;
 const peak=Math.max(...rows.map(r=>r.probability));
 const cap=[.01,.025,.05,.1,.2,.4,.6,.8,1].find(c=>c>=peak*1.05)??1;
 return {timestamp,cap,rows:rows.map((r,i)=>({...r,rank:rows.filter(p=>p.probability>r.probability).length+1,order:i}))};
}
export function contenderColumns(frame:NonNullable<ReturnType<typeof beforeContenders>>,selected:string,expanded=false){
 if(expanded)return frame.rows;
 const top=frame.rows.slice(0,4),pick=frame.rows.find(r=>r.name===selected);
 return pick&&!top.some(r=>r.id===pick.id)?[...top.slice(0,3),pick]:top;
}
