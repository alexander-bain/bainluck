import game from './game.json' with {type:'json'};

// Exact archived observations. Never synthesize missing clocks or scoring-play times.
export const nflGame = game;
const date = (s:string)=>Date.parse(s);
export const nflBaseline=game.series.filter(p=>date(p.timestamp)<date(game.commence_time)).at(-1)!;
export const nflMoments=[nflBaseline.timestamp,
 '2026-09-29T00:25:50.381605+00:00',
 '2026-09-29T01:38:50.628707+00:00',
 '2026-09-29T02:16:51.214009+00:00',
 '2026-09-29T03:11:51.541193+00:00',game.completed_at];
export type NFLCard='finish'|'rush'|'touchdowns';
export function nflContext(at:string){
 const time=date(at),final=time>=date(game.completed_at),pregame=time<date(game.commence_time);
 const states=game.game_states.filter(p=>date(p.timestamp)<=time);
 const state=states.at(-1)??null;
 const scores=game.score_history.filter(p=>date(p.timestamp)<=time);
 const score=scores.at(-1)??null;
 const periods=game.period_markers.filter(p=>date(p.timestamp)<=time);
 const projections=game.projections.filter(p=>date(p.timestamp)<=time&&p.projected_home_score!==null&&p.projected_away_score!==null);
 const lastProjection=projections.at(-1)??null;
 const projection=lastProjection&&date(lastProjection.valid_until)>time&&!final?lastProjection:null;
 const baseline={time:date(nflBaseline.timestamp),home:nflBaseline.home_probability,away:1-nflBaseline.home_probability};
 // Only pregame NFL is complemented, per the retained two-outcome source contract.
 // Every in-game pair below is read directly from the original game_states row.
 const history=[...(baseline.time<=time?[baseline]:[]),...states.map(p=>({time:date(p.timestamp),home:p.home_probability,away:p.away_probability}))];
 const point=history.at(-1)??null;
 const plotted=history.flatMap((p,i)=>i&&p.time-history[i-1].time>300000?[{time:p.time-1,home:null,away:null},p]:[p]);
 return {at,final,pregame,score,scores,state,periods,projection,lastProjection,history,plotted,point};
}
export function nflRank(final:boolean):NFLCard[]{return final?['touchdowns','rush','finish']:['finish','rush','touchdowns']}
// Adjacent score updates share a label at phone density; all raw checkpoints remain in details.
export function scoreClusters(scores:typeof game.score_history,width:number,visibleDomain?:[number,number]){
 const duration=visibleDomain?visibleDomain[1]-visibleDomain[0]:date(game.completed_at)-date(nflBaseline.timestamp);
 const result:{at:string;label:string;count:number;records:typeof scores}[]=[];
 for(const score of scores){
  const previous=result.at(-1);
  if(previous&&(date(score.timestamp)-date(previous.at))/duration*width<38){previous.at=score.timestamp;previous.label=`${score.home_score}–${score.away_score}`;previous.count++;previous.records.push(score)}
  else result.push({at:score.timestamp,label:`${score.home_score}–${score.away_score}`,count:1,records:[score]});
 }
 return result;
}

// Describe only the forecast admitted at the selected observation.
export function nflFinishCaption(c:ReturnType<typeof nflContext>){
 if(c.final)return 'Chicago beat the forecast.';
 if(!c.projection)return 'No recent projection.';
 if(c.pregame)return 'Philadelphia had the edge.';
 const home=c.projection.projected_home_score!,away=c.projection.projected_away_score!;
 return home>away?'The projected finish has flipped.':home<away?'Philadelphia is still projected ahead.':'The projected finish is level.';
}
