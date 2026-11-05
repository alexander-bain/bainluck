import {golfRows,golfPregame,golfScore} from './golfEvidence.ts';
import {placementRows,placementPregame,placementResult} from './placementEvidence.ts';
export type ArchiveGolfRole='win'|'top10';
export type ArchiveGolfPoint={t:number;value:number;volume:number;segment?:number|null;phase?:string|null;at:string};
export type ArchiveGolfChoice={id:string;name:string;source:string;before:{value:number;at:string}|null;result:boolean;resultLabel:string;score:string|null;history:ArchiveGolfPoint[]};
export const archiveGolfBands=['A–C','D–G','H–L','M–P','Q–S','T–Z'] as const;
export type ArchiveGolfBand=typeof archiveGolfBands[number];
const compare=(a:string,b:string)=>a<b?-1:a>b?1:0;
const normalize=(s:string)=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toUpperCase();
export function archiveGolfBand(name:string):ArchiveGolfBand {const c=normalize(name)[0]??'A';return c<='C'?'A–C':c<='G'?'D–G':c<='L'?'H–L':c<='P'?'M–P':c<='S'?'Q–S':'T–Z'}
export function archiveGolfChoices(role:ArchiveGolfRole):ArchiveGolfChoice[]{
 return role==='win'?golfRows.map(r=>({id:r.key,name:r.name,source:String(r.final.source),before:golfPregame(r.final),result:r.result,resultLabel:r.result?'Tournament winner':'Did not win',score:r.score===null?null:golfScore(r),history:r.history})):placementRows.map(r=>({id:r.key,name:r.name,source:r.source,before:placementPregame(r.final),result:r.result,resultLabel:placementResult(r),score:r.score,history:r.history}));
}
export function archiveGolfSuggestions(rows:ArchiveGolfChoice[],role:ArchiveGolfRole){
 const priced=rows.filter(r=>r.before&&Number.isFinite(r.before.value)&&r.before.value>=0&&r.before.value<=1);
 const high=[...priced].sort((a,b)=>b.before!.value-a.before!.value||compare(a.id,b.id));
 const picks=role==='win'?[...rows.filter(r=>r.result),...high]:[high[0],high.find(r=>!r.result),[...priced].filter(r=>r.result).sort((a,b)=>a.before!.value-b.before!.value||compare(a.id,b.id))[0],...high];
 const seen=new Set<string>(),result:ArchiveGolfChoice[]=[];
 for(const row of picks){if(!row||seen.has(row.id))continue;seen.add(row.id);result.push(row);if(result.length===3)break;}
 return result;
}
export function archiveGolfGroup(rows:ArchiveGolfChoice[],band:ArchiveGolfBand){return rows.filter(r=>archiveGolfBand(r.name)===band).sort((a,b)=>compare(normalize(a.name),normalize(b.name))||compare(a.source,b.source)||compare(a.id,b.id));}
export function archiveGolfPage(rows:ArchiveGolfChoice[],band:ArchiveGolfBand,page:number){
 const group=archiveGolfGroup(rows,band),pages=Math.max(1,Math.ceil(group.length/6)),current=Math.max(0,Math.min(pages-1,Number.isInteger(page)?page:0));
 return {rows:group.slice(current*6,current*6+6),page:current,pages,count:group.length,first:group.length?current*6+1:0,last:Math.min(group.length,current*6+6)};
}
export function archiveGolfPoints(row:ArchiveGolfChoice){
 const counts=new Map<number,number>();for(const p of row.history)counts.set(p.t,(counts.get(p.t)??0)+1);
 return row.history.filter(p=>counts.get(p.t)===1&&Number.isFinite(p.t)&&Number.isFinite(p.value)&&p.value>=0&&p.value<=1&&Number.isFinite(p.volume)&&p.volume>0&&Date.parse(p.at)/1000===p.t).sort((a,b)=>a.t-b.t);
}
export function archiveGolfFrame(rows:ArchiveGolfChoice[]){const times=rows.flatMap(r=>archiveGolfPoints(r).map(p=>p.t));return times.length?{from:Math.min(...times),through:Math.max(...times)}:null;}
export function archiveGolfPreview(row:ArchiveGolfChoice,frame:ReturnType<typeof archiveGolfFrame>){
 const points=archiveGolfPoints(row),segments:({x:number;y:number;before:boolean}[])[]=[];
 if(!frame)return {segments,last:null};
 const span=Math.max(1,frame.through-frame.from);
 let previous:ArchiveGolfPoint|undefined;
 for(const p of points){
  const value={x:(p.t-frame.from)/span,y:1-p.value,before:p.phase==='before'};
  if(previous&&p.segment!=null&&p.segment===previous.segment&&p.t-previous.t<=7200)segments.at(-1)!.push(value);else segments.push([value]);
  previous=p;
 }
 return {segments,last:points.at(-1)??null};
}

/** Zero-anchored closer scale; source prices and preview comparison frames never change. */
export function archiveGolfCeiling(values:readonly number[],full=false){
 const valid=values.filter(p=>Number.isFinite(p)&&p>=0&&p<=1);
 if(full||!valid.length)return 1;
 const target=Math.min(1,Math.max(.005,Math.max(...valid)*1.02));
 return [.01,.02,.05,.1,.2,.25,.5,.75,1].find(top=>top>=target)??1;
}
