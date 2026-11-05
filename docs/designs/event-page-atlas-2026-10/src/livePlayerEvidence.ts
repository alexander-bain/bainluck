export interface LiveMilestone {
 key:string; count:number; baseline:number|null; baselineAt:string|null; baselineBasis:string|null;
 recorded:number|null; recordedAt:string|null; deltaPoints:number|null; source:string;
 marketID:string; marketName:string; outcomeName:string;
}
export interface LivePlayerProfile {
 name:string; statKey:string; unit:string; period:string; actual:number|null;
 actualObservedAt:string|null; actualCapturedAt:string; defaultCount:number; points:LiveMilestone[];
}
export function validChance(value:number|null):number|null {
 return value!==null && Number.isFinite(value) && value>=0 && value<=1 ? value : null;
}
export function livePointSelection(point:LiveMilestone,actualValue:number|null,mode:string){
 const baseline=validChance(point.baseline);
 const recorded=mode==='captured'&&point.recordedAt&&Number.isFinite(Date.parse(point.recordedAt))?validChance(point.recorded):null;
 const actual=actualValue!==null&&Number.isFinite(actualValue)&&actualValue>=0?actualValue:null;
 return {point,baseline,recorded,actual,delta:recorded!==null&&baseline!==null?Math.round((recorded-baseline)*10000)/100:null,
  remaining:actual!==null?Math.max(0,point.count-actual):null};
}
export function livePlayerSelection(profile:LivePlayerProfile,count:number,mode:string){
 const matches=profile.points.filter(p=>p.count===count);
 return matches.length===1?livePointSelection(matches[0],profile.actual,mode):null;
}
function liveProfileScope(profile:LivePlayerProfile){return JSON.stringify([profile.name,profile.statKey,profile.unit,profile.period]);}
function liveMilestoneIdentity(point:LiveMilestone){return JSON.stringify([point.key,point.source,point.marketID,point.marketName,point.outcomeName,point.count]);}
export interface LivePlayerBookmark {scope:string;point:LiveMilestone}
export function livePlayerBookmark(profile:LivePlayerProfile,point:LiveMilestone):LivePlayerBookmark{return {scope:liveProfileScope(profile),point};}
export function resolveLivePlayerSelection(profile:LivePlayerProfile,bookmark:LivePlayerBookmark|null,mode:string){
 const anchor=bookmark??(profile.points.find(p=>p.count===profile.defaultCount)??profile.points[0]);
 if(!anchor)return null;
 const held='point' in anchor?anchor:livePlayerBookmark(profile,anchor);
 if(held.scope!==liveProfileScope(profile))return null;
 const matches=profile.points.filter(p=>liveMilestoneIdentity(p)===liveMilestoneIdentity(held.point));
 const present=matches.length===1;
 const point=present?matches[0]:held.point;
 return {...livePointSelection(point,profile.actual,present?mode:'stale'),present,ambiguous:matches.length>1};
}
