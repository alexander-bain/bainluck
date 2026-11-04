import wire from './aflwFinalScore.json' with {type:'json'};
import captures from './aflwCaptures.json' with {type:'json'};
export type AflwFinalWire=typeof wire;
export const aflPoints=(goals:number,behinds:number)=>goals*6+behinds;
export function qualifyAflwFinal(w:AflwFinalWire,event=captures.latestDetail){
 if(event.id!==15324784||w.eventID!==event.id||event.sport!=='aussierules_aflw'||w.sport!==event.sport||w.home!==event.home_team||w.away!==event.away_team||w.home!=='Sydney Swans'||w.away!=='Carlton Blues')return null;
 if(w.eventDate!=='2026-10-11'||!Number.isFinite(Date.parse(event.commence_time))||new Date(event.commence_time).toISOString().slice(0,10)!==w.eventDate||w.venue!=='Henson Park'||w.round!==9||w.state!=='final'||w.completedAt!==null||w.actualStartAt!==null)return null;
 if(JSON.stringify(w.homeQuarters)!=='[[1,3],[2,4],[3,4],[4,8]]'||JSON.stringify(w.awayQuarters)!=='[[4,3],[5,6],[6,10],[8,11]]')return null;
 if(w.source.publisher!=='AFL'||w.source.url!=='https://www.afl.com.au/aflw/news/1630336/carlton-blues-cruise-past-sydney-swans-to-as-good-as-lock-in-finals'||!/^[a-f0-9]{64}$/.test(w.source.sha256)||!Number.isFinite(Date.parse(w.source.capturedAt)))return null;
 const checkpoints=w.homeQuarters.map(([goals,behinds],i)=>({label:['Q1','Half','Q3','Final'][i],home:{goals,behinds,points:aflPoints(goals,behinds)},away:{goals:w.awayQuarters[i][0],behinds:w.awayQuarters[i][1],points:aflPoints(...w.awayQuarters[i] as [number,number])},at:null}));
 return {...w,checkpoints,homeScore:32,awayScore:59,winner:w.away,margin:27};
}
export const officialAflwFinal=qualifyAflwFinal(wire);
export function aflwFinalForDetail(detail:Record<string,unknown>){
 const r=officialAflwFinal;
 return r&&detail.id===r.eventID&&detail.sport===r.sport&&detail.home_team===r.home&&detail.away_team===r.away&&detail.commence_time===captures.latestDetail.commence_time&&detail.status==='completed'&&detail.home_score===r.homeScore&&detail.away_score===r.awayScore&&!detail.quality_hold?r:null;
}
