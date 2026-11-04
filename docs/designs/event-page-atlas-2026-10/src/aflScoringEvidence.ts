import capture from './aflScoringCapture.json' with {type:'json'};
import {aflScore,aflQuarters,aflWire,type AflPhase} from './aflMatchEvidence.ts';
export type AflScoringPoint={id:string;order:number;sequence:number;quarter:number;clock:string;seconds:number;brisbane:number;fremantle:number;margin:number;positive:number;negative:number;scorer:string;kind:string;team:'BRI'|'FRE';points:number};
export function aflScoringPlays(phase:AflPhase='final',wire=capture,base=aflWire):AflScoringPoint[]{
 const score=aflScore(phase,base),h=wire.header.competitions;
 if(!score||aflQuarters(phase,base).length!==4||wire.eventID!=='1133711'||wire.header.id!==wire.eventID||wire.wallclockAvailable!==false||h.length!==1||h[0].id!==wire.eventID||h[0].date!=='2026-09-26T04:30Z'||!h[0].status.type.completed||h[0].status.type.name!=='STATUS_FINAL'||!wire.plays.length)return [];
 const participants=h[0].competitors;
 if(participants.length!==2||!participants.some(t=>t.id==='11'&&t.homeAway==='away'&&t.score==='96'&&t.winner===true)||!participants.some(t=>t.id==='1'&&t.homeAway==='home'&&t.score==='89'&&t.winner===false))return [];
 const ids=new Set<string>(),out:AflScoringPoint[]=[];let bri=0,fre=0,quarter=1,seconds=0,seq=-1;
 for(const p of wire.plays){
  const q=p.period.number,match=/^(\d{1,2}):([0-5]\d)$/.exec(p.clock.displayValue),sequence=Number(p.sequenceNumber),newBri=p.awayScore,newFre=p.homeScore;
  if(!p.id||ids.has(p.id)||!Number.isSafeInteger(sequence)||sequence<=seq||!Number.isSafeInteger(q)||q<quarter||q>4||q<1||!match||![newBri,newFre].every(n=>Number.isSafeInteger(n)&&n>=0))return [];
  const elapsed=Number(match[1])*60+Number(match[2]);if(q===quarter&&elapsed<seconds)return [];
  const db=newBri-bri,df=newFre-fre,points=db+df,team=p.team.id==='11'?'BRI':p.team.id==='1'?'FRE':null;
  const kind=p.type.text,expected=kind==='Goal'?6:['Behind','Rushed'].includes(kind)?1:0;
  if(!team||points!==expected||expected===0||db<0||df<0||(team==='BRI'?(db!==points||df!==0):(df!==points||db!==0)))return [];
  ids.add(p.id);bri=newBri;fre=newFre;quarter=q;seconds=elapsed;seq=sequence;
  out.push({id:p.id,order:out.length+1,sequence,quarter:q,clock:p.clock.displayValue,seconds:elapsed,brisbane:bri,fremantle:fre,margin:bri-fre,positive:Math.max(0,bri-fre),negative:Math.min(0,bri-fre),scorer:p.text,kind,team,points});
 }
 if(bri!==score.brisbane||fre!==score.fremantle)return [];
 for(const t of score.teams)for(const line of t.linescores){const actual=out.filter(p=>p.quarter===line.period&&p.team===(t.id==='11'?'BRI':'FRE')).reduce((n,p)=>n+p.points,0);if(actual!==line.value)return [];}
 return out;
}
export function aflScoringStory(phase:AflPhase='final',wire=capture,base=aflWire){
 const plays=aflScoringPlays(phase,wire,base);if(!plays.length)return null;
 const low=plays.reduce((a,b)=>b.margin<a.margin?b:a),last=plays.at(-1)!;
 const run=plays.filter(p=>p.order>low.order);
 const fourGoals=run.length===4&&run.every(p=>p.team==='BRI'&&p.kind==='Goal'&&p.points===6);
 const quarterStarts=[1,2,3,4].map(q=>plays.find(p=>p.quarter===q)).filter((p):p is AflScoringPoint=>!!p);
 return {plays,low,last,run,fourGoals,quarterStarts,bound:Math.max(12,Math.ceil(Math.max(...plays.map(p=>Math.abs(p.margin)))/6)*6)};
}
export function aflScoringSelection(order:number,phase:AflPhase='final'){
 const story=aflScoringStory(phase);if(!story||!Number.isSafeInteger(order))return null;return story.plays.find(p=>p.order===order)??null;
}
