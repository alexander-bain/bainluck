import {ceremonyCapture as original,type AwardCapture,type AwardPhase} from './ceremonyEvidence.ts';
import {ceremonyStoryRank} from './ceremonyStoryRank.ts';
import {createStoryReadingFrame,storyReadingReducer,type StoryFrame,type StoryReadingAction,type StoryReadingFrame} from './storyReadingFrame.ts';
export interface CeremonyArrivalPayload {phase:AwardPhase;cutoff:number;capture:AwardCapture}
export type CeremonyArrivalFrame=StoryFrame<CeremonyArrivalPayload>;
export const ceremonyStoryIDs=['picture','actor'];
export function ceremonySnapshot(cutoff:number):AwardCapture{
 if(!Number.isSafeInteger(cutoff)||cutoff<original.baselineCutoff-1)throw Error('Invalid recorded cutoff');
 return {...original,races:original.races.map(r=>({...r,markets:r.markets.map(m=>({...m,sides:m.sides.map(s=>({...s,points:s.points.filter(p=>p.t<=cutoff).map(p=>({...p}))}))}))}))};
}
/** Real retained Yes-trade changes, not award announcements or a synthetic game clock. */
function cuts(){
 const trades=original.races.flatMap(r=>r.markets.flatMap(m=>m.sides.filter(s=>s.side==='Yes').flatMap(s=>s.points.map(p=>({market:m.id,p}))))).filter(t=>t.p.t>=original.baselineCutoff).sort((a,b)=>a.p.t-b.p.t);
 const baselines=new Map(original.races.flatMap(r=>r.markets.flatMap(m=>{const b=m.sides.find(s=>s.side==='Yes')!.points.filter(p=>p.t<original.baselineCutoff).at(-1);return b?[[m.id,b.p] as const]:[]})));
 const last=new Map<string,number>(),raceOf=new Map(original.races.flatMap(r=>r.markets.map(m=>[m.id,r.id] as const)));
 const selected=[original.baselineCutoff];let prior='';
 for(let i=0;i<trades.length;i++){
  const {market,p}=trades[i];last.set(market,p.p);if(trades[i+1]?.p.t===p.t)continue;
  const scores=original.races.map(r=>({id:r.id,score:Math.max(0,...[...last].filter(([id])=>raceOf.get(id)===r.id&&baselines.has(id)).map(([id,p])=>Math.abs(p-baselines.get(id)!)))})).sort((a,b)=>b.score-a.score||b.id.localeCompare(a.id));
  const key=scores.map(s=>s.id).join('|');if(key!==prior){selected.push(p.t);prior=key;}
 }
 if(trades.length)selected.push(trades[0].p.t);
 selected.push(Math.max(...original.races.flatMap(r=>r.markets.flatMap(m=>m.sides.flatMap(s=>s.points.map(p=>p.t))))));
 return [...new Set(selected)].sort((a,b)=>a-b);
}
export const ceremonyArrivalCutoffs=cuts();
export function ceremonyArrivalFrame(index:number,phase:AwardPhase='final'):CeremonyArrivalFrame{
 const sequence=phase==='before'?0:Math.min(ceremonyArrivalCutoffs.length-1,Math.max(0,Math.floor(index)));
 const cutoff=phase==='before'?original.baselineCutoff-1:ceremonyArrivalCutoffs[sequence],capture=ceremonySnapshot(cutoff);
 return {scope:'ceremony400:'+phase,sequence,through:new Date(cutoff*1000).toISOString(),order:ceremonyStoryRank(phase,capture).map(r=>r.id),payload:{phase,cutoff,capture}};
}
export function validCeremonyArrival(frame:CeremonyArrivalFrame){
 try{
  const p=frame.payload;if(!p||!['before','final'].includes(p.phase)||frame.scope!=='ceremony400:'+p.phase||frame.through!==new Date(p.cutoff*1000).toISOString())return false;
  const expected=ceremonyArrivalFrame(frame.sequence,p.phase);
  return frame.sequence===expected.sequence&&frame.through===expected.through&&JSON.stringify(frame.order)===JSON.stringify(expected.order)&&JSON.stringify(p.capture)===JSON.stringify(expected.payload.capture);
 }catch{return false}
}
export function createCeremonyArrival(phase:AwardPhase='final',latest=true){const state=createStoryReadingFrame(ceremonyArrivalFrame(latest?ceremonyArrivalCutoffs.length-1:0,phase),ceremonyStoryIDs);return latest?{...state,stream:{...state.stream,held:false}}:state}
export function ceremonyArrivalReducer(state:StoryReadingFrame<CeremonyArrivalPayload>,action:StoryReadingAction<CeremonyArrivalPayload>){
 if(action.type==='refresh'&&state.locks.length)return state;
 if((action.type==='receive'||action.type==='inspect')&&!validCeremonyArrival(action.frame))return state;
 return storyReadingReducer(state,action);
}
