import {journeyNames,journeyFor,windowPoints} from './golfJourneyEvidence.ts';
/** Compare exactly two shared recorded snapshots, never interpolated history. */
export function golfBeforeMovement(through?:string){
 const rows=journeyNames.flatMap(name=>{
  const original=journeyFor(name)?.original;
  const points=windowPoints(name,'Pre',through).filter(p=>Number.isFinite(Date.parse(p.timestamp))&&Number.isFinite(p.probability)&&p.probability>=0&&p.probability<=1);
  return original&&points.length?[{name,id:original.id,points}]:[];
 });
 if(!rows.length)return null;
 const shared=rows[0].points.map(p=>p.timestamp).filter(at=>rows.every(r=>r.points.filter(p=>p.timestamp===at).length===1)).sort((a,b)=>Date.parse(a)-Date.parse(b));
 if(shared.length<2)return null;
 const earlier=shared.at(-2)!,later=shared.at(-1)!;
 if(Date.parse(later)<=Date.parse(earlier))return null;
 const compared=rows.map(r=>{const first=r.points.find(p=>p.timestamp===earlier)!,last=r.points.find(p=>p.timestamp===later)!;return {name:r.name,id:r.id,first,last,change:last.probability-first.probability}});
 return {earlier,later,rows:compared.sort((a,b)=>Math.abs(b.change)-Math.abs(a.change)||a.name.localeCompare(b.name))};
}
export function beforeMovementRows(comparison:NonNullable<ReturnType<typeof golfBeforeMovement>>,selected:string){
 const pick=comparison.rows.find(r=>r.name===selected),top=comparison.rows.slice(0,4);
 return pick&&!top.some(r=>r.id===pick.id)?[...top.slice(0,3),pick]:top;
}
export function beforeMovementScale(comparison:NonNullable<ReturnType<typeof golfBeforeMovement>>){
 const peak=Math.max(...comparison.rows.map(r=>Math.abs(r.change)));
 return [.0005,.001,.0025,.005,.01,.025,.05,.1,.25,.5,1].find(cap=>cap>=peak*1.02)??1;
}
export function movementLabel(change:number){const n=Math.abs(change)*100;return change===0?'No change':`${change>0?'+':'−'}${n<.01?'<0.01':n.toFixed(2)} pts`;}
