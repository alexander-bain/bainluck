import recorded from './curling-end-context.json' with {type:'json'};
import {curlingCapture, type CurlingPhase} from './curlingEvidence.ts';
type Team='SWE'|'CHE';
export type CurlingEndContext={end:number;page:number;lastThrow:Team;thinkingSeconds:Record<Team,number>};
const isRecord=(v:unknown):v is Record<string,unknown>=>typeof v==='object'&&v!==null&&!Array.isArray(v);
const isTeam=(v:unknown):v is Team=>v==='SWE'||v==='CHE';
/** Optional archive context. Failure never removes independently admitted score/history. */
export function admitCurlingEndContext(input:unknown,phase:CurlingPhase,end:number):CurlingEndContext|null{
 if(phase!=='final'||!Number.isInteger(end)||end<1||end>10||!isRecord(input))return null;
 if(input.eventTicker!=='KXWOCURLGAME-26FEB22SWECHE'||input.gameCode!=='CURWTEAM4-------------FNL-000101--'||input.date!=='2026-02-22')return null;
 if(!isRecord(input.source)||input.source.sha256!=='88739abc0af0f5174a32529fddf9c4dc39ee8a6544bad338a5bf19b961561b41'||!Array.isArray(input.ends))return null;
 const rows=input.ends.filter(r=>isRecord(r)&&r.end===end);if(rows.length!==1)return null;
 const r=rows[0];if(!isRecord(r)||r.page!==11+end||!Array.isArray(r.shots)||r.shots.length!==16||!isRecord(r.score)||!isRecord(r.thinkingSeconds))return null;
 let previous:Team|null=null;const count={SWE:0,CHE:0};
 for(let i=0;i<16;i++){const s=r.shots[i];if(!isRecord(s)||s.number!==i+1||!isTeam(s.team)||s.team===previous)return null;previous=s.team;count[s.team]++;}
 if(count.SWE!==8||count.CHE!==8||!previous)return null;
 const clocks={} as Record<Team,number>;
 for(const [i,team] of (['SWE','CHE'] as const).entries()){
  if(r.score[team]!==curlingCapture.teams[i].scores.slice(0,end).reduce((a,b)=>a+b,0))return null;
  const seconds=r.thinkingSeconds[team];if(typeof seconds!=='number'||!Number.isInteger(seconds)||seconds<0||seconds>38*60)return null;clocks[team]=seconds;
 }
 return {end,page:11+end,lastThrow:previous,thinkingSeconds:clocks};
}
export const curlingEndContext=(phase:CurlingPhase,end:number)=>admitCurlingEndContext(recorded,phase,end);
export const curlingTeamName=(team:Team)=>team==='SWE'?'Sweden':'Switzerland';
export function curlingEndSummary(end:number,scored:number[]){
 if(end===10)return 'Sweden takes gold';
 const team=scored.findIndex(n=>n>0);return team<0?'No points scored':`${team===0?'Sweden':'Switzerland'} scores ${scored[team]}`;
}
export function curlingThinkingClock(seconds:number){return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;}
