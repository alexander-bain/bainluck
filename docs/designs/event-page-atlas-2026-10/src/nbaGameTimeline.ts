import record from './nbaQuarterRecords.json' with {type:'json'};
import type {FinalHistoryPoint,FinalHistoryWire} from './finalHistoryEvidence';
import {finalHistoryScope,type FinalHistoryScope} from './finalHistoryEvidence.ts';

type Context={homeScore:number;awayScore:number}|null;
export type NBALandmark={id:string;label:string;description:string;t:number;at:string;playID:string;homeScore:number;awayScore:number};
export type NBATimeline={tip:NBALandmark;final:NBALandmark;markers:NBALandmark[];listedStart:number};

/** One archived game's admitted timing overlay; not a production event adapter. */
export function nbaGameTimeline(wire:FinalHistoryWire|undefined,context:Context,evidence=record):NBATimeline|null {
 if(!wire||!context||wire.key!=='nba'||wire.event_id!==15320337||evidence.eventID!==wire.event_id||evidence.providerID!=='401918010'||wire.home_team!==evidence.home.name||wire.away_team!==evidence.away.name||evidence.home.id!=='12'||evidence.away.id!=='9'||context.homeScore!==evidence.home.score||context.awayScore!==evidence.away.score||!evidence.completed)return null;
 const listedStart=Date.parse(evidence.listedStart);
 if(!Number.isFinite(listedStart)||listedStart!==Date.parse(wire.commence_time))return null;
 const tip=evidence.openingTip,ends=evidence.periodEnds;
 if(tip.type.id!=='615'||tip.period.number!==1||tip.clock.displayValue!=='12:00'||tip.homeScore!==0||tip.awayScore!==0||ends.length!==4)return null;
 const plays=[tip,...ends],times=plays.map(p=>Date.parse(p.wallclock));
 if(times.some(t=>!Number.isFinite(t))||times[0]<listedStart||times.some((t,i)=>i>0&&t<=times[i-1])||new Set(plays.map(p=>p.id)).size!==5)return null;
 if(plays.some(p=>p.id!==evidence.providerID+p.sequenceNumber||!Number.isInteger(p.homeScore)||!Number.isInteger(p.awayScore)||p.homeScore<0||p.awayScore<0))return null;
 for(const [i,p] of ends.entries())if(p.type.id!=='412'||p.period.number!==i+1||p.clock.displayValue!=='0.0'||p.homeScore<plays[i].homeScore||p.awayScore<plays[i].awayScore)return null;
 const end=ends[3];if(end.homeScore!==context.homeScore||end.awayScore!==context.awayScore)return null;
 const labels=['Tip','Q1 end','Half','Q3 end','Final'],descriptions=['Opening tip','First quarter ended','Halftime · second quarter ended','Third quarter ended','Fourth quarter ended · final'];
 const markers=plays.map((p,i)=>({id:i===0?'tip':`q${i}`,label:labels[i],description:descriptions[i],t:times[i],at:p.wallclock,playID:p.id,homeScore:p.homeScore,awayScore:p.awayScore}));
 return {tip:markers[0],final:markers[4],markers,listedStart};
}

/** Reclassify timing only; every probability, timestamp, index and gap stays original. */
export function nbaTimedHistory(points:FinalHistoryPoint[],timeline:NBATimeline|null){
 return timeline?points.map(p=>({...p,pregame:p.t<timeline.tip.t})):points;
}

/** Post-play observations remain in All, never the default game journey. */
export function nbaTimelineScope(points:FinalHistoryPoint[],scope:FinalHistoryScope,timeline:NBATimeline|null){
 return finalHistoryScope(timeline&&scope==='game'?points.filter(p=>p.t<=timeline.final.t):points,scope);
}

export function nbaHistoryPhase(t:number,timeline:NBATimeline|null){
 if(!timeline)return 'Recorded chance';
 return t<timeline.tip.t?'○ Recorded before tip-off':t>=timeline.final.t?'● Recorded after play':'● Recorded in game';
}

/** A landmark selects an existing reading at/before it within the retained five-minute bound. */
export function nbaLandmarkReading(points:FinalHistoryPoint[],marker:NBALandmark){
 let i=points.length-1;while(i>=0&&points[i].t>marker.t)i--;
 return i>=0&&marker.t-points[i].t<=300000?i:null;
}

export function nbaPlotLandmarks(timeline:NBATimeline|null,points:FinalHistoryPoint[],scope:string){
 if(!timeline||!points.length)return [];
 const candidates=scope==='game'?timeline.markers:[timeline.tip];
 return candidates.filter(m=>m.t>=points[0].t&&m.t<=points.at(-1)!.t);
}
