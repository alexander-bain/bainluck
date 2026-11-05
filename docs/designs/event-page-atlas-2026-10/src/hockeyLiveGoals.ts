import raw from './hockeyLiveGoals.json' with {type:'json'};
import {hockeyLiveSnapshot,type HockeyLiveWire,type HockeyLiveProp} from './hockeyLive.ts';
export type HockeyGoalAvailability='recent'|'reached'|'after_goal'|'stale'|'missing';
export type HockeyLiveGoalsWire=typeof raw;
type Observation={t:number;at:string;value:number;volume:number|null;kind?:string};
type DisplayProp=Omit<HockeyLiveProp,'last'|'recent'>&{last:Observation|null;recent:Observation|null};
export function hockeyLiveGoalsSnapshot(index:number,w:HockeyLiveGoalsWire=raw){
 if(w.eventID!==15169793||w.espnID!=='401891814')return null;
 const frame=hockeyLiveSnapshot(index,w.base as HockeyLiveWire);if(!frame)return null;
 const goalTimes=w.goals.filter(g=>g.t<=frame.stage.t).map(g=>g.t),latestGoal=goalTimes.length?Math.max(...goalTimes):null;
 const props=frame.props.map(original=>{
  const matches=w.records.filter(r=>r.key===original.key&&r.family===original.family&&r.marketID===original.marketID);
  const record=matches.length===1?matches[0]:null;
  let prop:DisplayProp=original;
  if(record){
   const valid=record.family==='totals'?original.threshold===record.threshold&&record.marketID===63539066:record.family==='scorers'&&record.threshold===1&&record.marketID===64870965&&original.title===record.player+': 1+';
   if(valid){
    const observations=record.observations.filter(o=>o.t>=Date.parse(w.base.recordedStart)/1000&&o.t<=frame.stage.t&&Date.parse(o.at)/1000===o.t&&o.value>=0&&o.value<=1&&record.observations.filter(p=>p.t===o.t).length===1&&(record.family==='totals'?o.kind==='consensus'&&o.volume===null&&o.value>0&&o.value<1:o.kind==='trade'&&typeof o.volume==='number'&&o.volume>0));
    const last=observations.reduce((a,o)=>!a||o.t>a.t?o:a,null as typeof observations[number]|null);
    const recent=last&&frame.stage.t-last.t<=300?last:null;
    const people=record.playerID?frame.stage.stats.filter(p=>p.id===record.playerID&&p.name===record.player&&p.team===(record.team==='home'?'Minnesota Wild':'Boston Bruins')):[];
    const person=people.length===1?people[0]:null;
    const stats=person&&person.goals>=0&&person.assists>=0&&person.points===person.goals+person.assists?{goals:person.goals,assists:person.assists,points:person.points}:null;
    prop={...original,player:record.player,team:record.team,threshold:record.threshold,actual:record.family==='totals'?frame.stage.score[0]+frame.stage.score[1]:stats?.goals??null,stats,ticker:record.ticker,rules:record.rules??original.rules,last,recent};
   }
  }
  const reached=prop.actual!==null&&prop.threshold!==null&&prop.actual>=prop.threshold;
  const afterGoal=!reached&&prop.last!==null&&latestGoal!==null&&prop.last.t<latestGoal;
  const availability:HockeyGoalAvailability=reached?'reached':afterGoal?'after_goal':prop.recent?'recent':prop.last?'stale':'missing';
  return {...prop,recent:availability==='recent'?prop.recent:null,availability,latestGoal};
 });
 const chance=frame.chance&&latestGoal!==null&&frame.chance.t<latestGoal?null:frame.chance;
 return {...frame,props,chance,latestGoal};
}
export type HockeyLiveGoalProp=NonNullable<ReturnType<typeof hockeyLiveGoalsSnapshot>>['props'][number];
export function hockeyGoalActual(p:HockeyLiveGoalProp){if(p.actual===null)return 'Unavailable';const unit=p.family==='points'?'point':p.family==='assists'?'assist':'goal';return p.actual+' '+unit+(p.actual===1?'':'s');}
export const hockeyGoalAvailability=(p:HockeyLiveGoalProp)=>p.availability==='reached'?'Milestone reached':p.availability==='after_goal'?'No update since goal':'No recent probability update';
export function liveGoalLeaders(props:HockeyLiveGoalProp[],selected:string|null){
 const all=props.filter(p=>p.family==='scorers').sort((a,b)=>(b.actual??-1)-(a.actual??-1)||(b.baseline?.value??-1)-(a.baseline?.value??-1)||a.title.localeCompare(b.title));
 const first=all.slice(0,6),p=all.find(p=>p.key===selected);return p&&!first.includes(p)?[...first.slice(0,5),p]:first;
}
export {raw as hockeyLiveGoals};
