import {readerTime} from './readerTime.ts';
import {probabilityLabel} from './probabilityLabel.ts';
import raw from './golfJourney.json' with {type:'json'};
export const journeyWire=raw;
export const journeyNames=raw.market.outcomes.map(r=>r.name);
export const journeyClock=readerTime;
export const chance=probabilityLabel;
export const score=(v:number)=>v===0?'E':v>0?`+${v}`:`${v}`;
export function journeyFor(name:string){
 const originals=raw.market.outcomes.filter(r=>r.name===name);if(originals.length!==1)return null;
 const original=originals[0],series=raw.history.outcomes.filter(r=>r.outcome_id===original.id&&r.name===name);
 const observations=series.length===1?series[0].history:[];
 const valid=observations.filter(p=>Number.isFinite(p.probability)&&p.probability>=0&&p.probability<=1);
 const baseline=valid.filter(p=>Date.parse(p.timestamp)<Date.parse(raw.start)).at(-1)??null;
 const during=valid.filter(p=>Date.parse(p.timestamp)>=Date.parse(raw.start)&&Date.parse(p.timestamp)<=Date.parse(raw.terminalObservation.timestamp));
 const later=valid.filter(p=>Date.parse(p.timestamp)>Date.parse(raw.terminalObservation.timestamp));
 const uncertain=during.filter(p=>p.probability<1),peak=uncertain.reduce<typeof during[number]|null>((a,p)=>!a||p.probability>a.probability?p:a,null);
 const candidates=raw.final.players.filter(r=>r.name===name),anchors=raw.history.leaderboard.filter(r=>r.name===name);
 const final=candidates.length===1&&anchors.length===1&&candidates[0].total_score_raw===anchors[0].total_score&&candidates[0].today_raw===anchors[0].today_score&&candidates[0].position===anchors[0].position?{...candidates[0],dg_id:anchors[0].dg_id}:null;
 return {original,observations,baseline,during,later,peak,final};
}
export const closingField=raw.final.players.filter(p=>p.current_round===4&&p.thru==='18'&&Number.isFinite(p.today_raw));
export function journeySegments(points:{timestamp:string;probability:number}[]){const segments:typeof points[]=[];for(const p of points){const last=segments.at(-1);if(!last||Date.parse(p.timestamp)-Date.parse(last.at(-1)!.timestamp)>30*60*1000)segments.push([p]);else last.push(p)}return segments}
export type JourneyWindow='Pre'|'R1'|'R2'|'R3'|'R4'|'All';
export const journeyWindows:JourneyWindow[]=['Pre','R1','R2','R3','R4','All'];
function allWindowPoints(name:string,window:JourneyWindow){const row=journeyFor(name);if(!row)return[];if(window==='Pre')return row.observations.filter(p=>Date.parse(p.timestamp)<Date.parse(raw.start));if(window==='All')return row.during;const i=raw.history.round_boundaries.findIndex(b=>b.label===window);if(i<0)return[];const start=Date.parse(raw.history.round_boundaries[i].timestamp),end=i===3?Date.parse(raw.terminalObservation.timestamp)+1:Date.parse(raw.history.round_boundaries[i+1].timestamp);return row.during.filter(p=>Date.parse(p.timestamp)>=start&&Date.parse(p.timestamp)<end)}
export function windowPoints(name:string,window:JourneyWindow,through?:string){const points=allWindowPoints(name,window);return through?points.filter(p=>Date.parse(p.timestamp)<=Date.parse(through)):points}
export function featuredGolfers(window:JourneyWindow,pinned:string|null,through?:string){
 const ranked=raw.history.outcomes.map(r=>{const points=windowPoints(r.name,window,through);const first=points[0]?.probability??0,last=points.at(-1)?.probability??0;return {name:r.name,score:last+Math.abs(last-first)*.35,available:points.length>0}}).filter(r=>r.available).sort((a,b)=>b.score-a.score||a.name.localeCompare(b.name));
 return [...new Set([...(pinned?[pinned]:[]),...ranked.map(r=>r.name)])].slice(0,3);
}
export function chartCeiling(names:string[],window:JourneyWindow,full=false,through?:string){if(full)return 1;const peak=Math.max(0,...names.flatMap(n=>windowPoints(n,window,through).map(p=>p.probability)));return [0.025,0.05,0.1,0.15,0.2,0.25,0.4,0.6,0.8,1].find(v=>v>=peak*1.04)??1}
export function compressedTime(points:{timestamp:string}[],compress=true){
 const times=[...new Set(points.map(p=>Date.parse(p.timestamp)))].sort((a,b)=>a-b),start=times[0]??0,end=times.at(-1)??start;
 const gaps=times.slice(1).flatMap((t,i)=>t-times[i]>3600000?[{start:times[i],end:t,kept:compress?1200000:t-times[i]}]:[]);
 const offset=(t:number)=>t-start-gaps.reduce((n,g)=>n+(t<=g.start?0:(Math.min(t,g.end)-g.start)*(1-g.kept/(g.end-g.start))),0);
 const span=Math.max(1,offset(end));return {start,end,gaps,fraction:(t:number)=>offset(t)/span};
}

/** A shared tournament clock must not change when the visible golfer cohort changes.
 * Only captured, qualified observations in the displayed window/prefix set the domain.
 * These are observation boundaries, not tee times or proof of a break in play.
 */
export function tournamentTimeline(window:JourneyWindow,through?:string){
 const points=journeyNames.flatMap(name=>windowPoints(name,window,through)).filter(p=>Number.isFinite(Date.parse(p.timestamp))&&Number.isFinite(p.probability)&&p.probability>=0&&p.probability<=1);
 return compressedTime(points,window!=='Pre');
}
