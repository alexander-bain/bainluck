import {curlingCapture,curlingBaseline,type CurlingPhase} from './curlingEvidence.ts';
/** Actual end counts; deliberately no clock, probability or hammer interpolation. */
export function curlingEndPath(phase:CurlingPhase){
 if(phase!=='final')return [];
 const teams=curlingCapture.teams;
 return Array.from({length:10},(_,i)=>{
  const sweden=teams[0].scores.slice(0,i+1).reduce((a,b)=>a+b,0),switzerland=teams[1].scores.slice(0,i+1).reduce((a,b)=>a+b,0);
  return {end:i+1,sweden,switzerland,lead:sweden-switzerland,scored:teams.map(t=>t.scores[i])};
 });
}
export function curlingEnd(phase:CurlingPhase,end:number){return Number.isInteger(end)?curlingEndPath(phase).find(p=>p.end===end)??null:null;}
export const curlingPreMatch=curlingCapture.teams.map((t,i)=>({name:t.name,code:t.code,point:curlingBaseline(i)}));
