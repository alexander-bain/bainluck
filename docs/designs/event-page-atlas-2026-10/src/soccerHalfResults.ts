import live from './liveSoccer.json' with {type:'json'};
import final from './soccerFinal.json' with {type:'json'};
import type {FinalSoccerRow} from './soccerFinalEvidence.ts';
export const halfBindings=[
 {id:'first',name:'First half',market:63178219,ids:[242338171,242338170,242338172]},
 {id:'second',name:'Second half',market:63178218,ids:[246041831,245875499,245681743]},
] as const;
export const halfCompetitors=[{id:'home',label:'Valladolid',original:'Real Valladolid CF'},{id:'draw',label:'Draw',original:'Draw'},{id:'away',label:'Albacete',original:'Albacete Balompié'}] as const;
export type HalfCompetitor=typeof halfCompetitors[number]['id'];
export type HalfPhase='before'|'in-match'|'final';
export function admitHalfComparison(capture:{eventID:number;start:string;rows:FinalSoccerRow[]},phase:HalfPhase){
 if(!['before','in-match','final'].includes(phase))return null;
 if(capture.eventID!==15325054||!Number.isFinite(Date.parse(capture.start)))return null;
 const halves=halfBindings.map(half=>{
  const rows=halfCompetitors.map((team,index)=>capture.rows.filter(r=>r.marketID===half.market&&r.outcomeIDs.length===1&&r.outcomeIDs[0]===half.ids[index]&&r.label===team.original));
  if(rows.some(r=>r.length!==1))return null;
  const outcomes=rows.map(r=>r[0]);
  if(phase==='final'&&(outcomes.some(r=>!['won','lost'].includes(r.result)||!r.resultEvidence)||outcomes.filter(r=>r.result==='won').length!==1))return null;
  return {...half,outcomes:outcomes.map((row,index)=>({team:halfCompetitors[index],row:phase==='final'?row:{...row,result:'unconfirmed',resultEvidence:null},value:row.baseline&&Number.isFinite(row.baseline.value)&&row.baseline.value>=0&&row.baseline.value<=1&&Date.parse(row.baseline.at)<Date.parse(capture.start)?row.baseline.value:null}))};
 });
 return halves.every(h=>h!==null)?halves:null;
}

export function admitHalfResults(capture:{eventID:number;start:string;rows:FinalSoccerRow[]}){return admitHalfComparison(capture,'final')}
export function soccerHalfSnapshot(phase:HalfPhase){return admitHalfComparison(phase==='final'?final:{...live,rows:live.rows.map(row=>({...row,result:'unconfirmed',resultEvidence:null}))},phase)}
