import {nflGame,nflBaseline,type nflContext} from './nflReplay.ts';

type Context=ReturnType<typeof nflContext>;
export type TimelinePoint={time:number;home:number;away:number};
const time=(value:string)=>Date.parse(value);
const sixHours=6*60*60*1000;
/** Plot geometry follows the displayed frame, never a newer received frame.
 * Pregame uses the archived NFL two-outcome aggregate contract in game.provenance.
 * In-game pairs are the explicit home/away observations from nflContext. */
export function nflTimeline(context:Context){
 const through=time(context.at);
 const history:TimelinePoint[]=context.pregame
  ?nflGame.series.filter(p=>time(p.timestamp)<=through&&time(p.timestamp)<time(nflGame.commence_time)&&time(p.timestamp)>=through-sixHours)
   .map(p=>({time:time(p.timestamp),home:p.home_probability,away:1-p.home_probability}))
  :context.history;
 const first=history[0]?.time??through;
 const latest=Math.max(history.at(-1)?.time??first,...context.scores.map(s=>time(s.timestamp)),...context.periods.map(p=>time(p.timestamp)));
 // Single-observation fallback supplies axis space only, never a synthetic quote.
 const domain:[number,number]=[first,Math.max(first+60_000,latest)];
 const plotted=history.flatMap((p,i)=>i&&p.time-history[i-1].time>300_000?[{time:p.time-1,home:null,away:null},p]:[p]);
 const ticks=latest>first?[first,first+(latest-first)/2,latest]:[first];
 return {history,plotted,domain,ticks,baselineAt:time(nflBaseline.timestamp),
  label:context.pregame?'Before kickoff · last 6 hours':context.final?'Complete game':'Game so far'};
}
