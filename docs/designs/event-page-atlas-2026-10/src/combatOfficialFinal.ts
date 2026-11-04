import raw from './combatOfficialFinal.json' with {type:'json'};
import history from './combatWinnerHistory.json' with {type:'json'};
export type CombatFinalWire=typeof raw;
type BoutIdentity={event_id:number;home_team:string;away_team:string;commence_time:string};
/** Design-only source correspondence; no production event/status mutation. */
export function qualifyCombatFinal(w:CombatFinalWire,event:BoutIdentity){
 if(w.eventID!==15318681||event.event_id!==w.eventID||w.home!==event.home_team||w.away!==event.away_team||w.home!=='Ateba Gautier'||w.away!=='Roman Kopylov')return null;
 if(w.eventName!=='UFC 332: Silva vs Wang'||w.venueTimeZone!=='America/Denver'||!Number.isFinite(Date.parse(event.commence_time)))return null;
 const localDate=new Intl.DateTimeFormat('en-CA',{timeZone:w.venueTimeZone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(event.commence_time));
 if(w.eventDate!=='2026-10-03'||localDate!==w.eventDate||w.winner!==w.away||w.loser!==w.home||w.method!=='TKO'||w.methodDetail!=='strikes'||w.round!==1||w.elapsedInRound!=='3:12'||w.absoluteFinishAt!==null)return null;
 if(w.source.publisher!=='UFC'||w.source.url!=='https://www.ufc.com/news/ufc-332-silva-vs-wang-results'||w.source.resultStatement!=='Roman Kopylov defeated Ateba Gautier by TKO (strikes) at 3:12 of Round 1'||!/^[a-f0-9]{64}$/.test(w.source.sha256)||!Number.isFinite(Date.parse(w.source.capturedAt)))return null;
 return {...w,winnerSide:'away' as const,finishLabel:'TKO · Round 1 · 3:12',elapsedSeconds:192};
}
export const officialCombatFinal=qualifyCombatFinal(raw,history);
export const combatFinalFor=(eventID:number)=>eventID===raw.eventID?officialCombatFinal:null;
