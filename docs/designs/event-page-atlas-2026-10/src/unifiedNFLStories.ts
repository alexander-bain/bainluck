import {receptionProfile,receptionID} from './receptionCounts.ts';
import {combinedNames,combinedProfile,combinedResult} from './combinedYardage.ts';
import {teamMilestoneKinds,teamMilestones,teamMilestoneDefinitions} from './teamMilestones.ts';

export type NFLStoryID=`yards:${string}`|`team:${typeof teamMilestoneKinds[number]}`|typeof receptionID;
export interface NFLStoryCandidate {id:NFLStoryID;family:'yards'|'team'|'catches';name:string;score:number|null;originals:string[]}
/** Same event, fixed archive. No inference of a count from a contract result. */
export function nflStoryCandidates(phase:string):NFLStoryCandidate[]{
 const yards=combinedNames.flatMap(name=>{
  const p=combinedProfile(name,phase);if(!p)return [];
  const scores=p.points.flatMap(q=>{
   if(q.baseline===null)return [];
   if(phase!=='Final')return [q.baseline];
   const result=combinedResult(q.row,phase);
   return result==='Happened'?[1-q.baseline]:result==='Didn’t happen'?[q.baseline]:[];
  });
  return [{id:`yards:${name}` as NFLStoryID,family:'yards' as const,name:name+' · ground + air',score:scores.length?Math.max(...scores):null,originals:p.points.map(q=>q.row.row_key)}];
 });
 const teams=teamMilestoneKinds.flatMap(kind=>{
  const p=teamMilestones(kind,phase);if(!p)return [];
  const points=p.profiles.flatMap(t=>t.points),scores=points.flatMap(q=>q.baseline===null?[]:phase!=='Final'?[q.baseline]:q.result==='Hit'?[1-q.baseline]:q.result==='Missed'?[q.baseline]:[]);
  return [{id:`team:${kind}` as NFLStoryID,family:'team' as const,name:teamMilestoneDefinitions[kind].name,score:scores.length?Math.max(...scores):null,originals:points.map(q=>q.row.row_key)}];
 });
 const reception=receptionProfile(phase);
 const catches:NFLStoryCandidate[]=reception?[{id:receptionID,family:'catches',name:'Dontayvion Wicks · catches',score:reception.score,originals:reception.points.flatMap(q=>[q.over.row_key,q.under.row_key])}]:[];
 return [...yards,...teams,...catches];
}
/** Probability-based editorial ordering with a small adjacent-family penalty.
 * Inputs stay intact; a missing comparison cannot earn a surprise score.
 * This is a deterministic design policy, not a connected AI ranking service.
 */
export function rankNFLStories(candidates:readonly NFLStoryCandidate[]):NFLStoryID[]{
 const remaining=candidates.filter((c,i)=>candidates.findIndex(x=>x.id===c.id)===i).map(c=>({...c}));
 const order:NFLStoryID[]=[];let previous:NFLStoryCandidate['family']|null=null;
 while(remaining.length){
  const score=(c:NFLStoryCandidate)=>(c.score!==null&&Number.isFinite(c.score)&&c.score>=0&&c.score<=1?c.score:-1)-(c.family===previous?0.15:0);
  remaining.sort((a,b)=>score(b)-score(a)||a.id.localeCompare(b.id));
  const next=remaining.shift()!;order.push(next.id);previous=next.family;
 }
 return order;
}
export function nflStoryOrder(phase:string){return rankNFLStories(nflStoryCandidates(phase))}
/** Only order/availability is simulated. Probabilities, actuals and source rows never change. */
export function previewNFLOrder(phase:string,mode:string){const order=nflStoryOrder(phase);return mode==='none'?[]:mode==='reverse'?[...order].reverse():order}
