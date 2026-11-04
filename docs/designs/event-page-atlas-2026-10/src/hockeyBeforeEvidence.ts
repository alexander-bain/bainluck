import {hockeyContribution} from './hockeyContributions.ts';
import atlas from './atlas.json' with {type:'json'};
import {finalHistoryWires,finalHistoryEvidence} from './finalHistoryEvidence.ts';
import {hockeyEvidence,hockeyPregame} from './hockeyEvidence.ts';
import {scorerPregameEvidence,scorerPregame} from './hockeyScorerPregame.ts';
import {firstScorerPregameEvidence,firstScorerPregame} from './hockeyFirstPregame.ts';
export type BeforeProp={key:string;title:string;market:string;source:string;marketID:number|null;contributors:number[];family:'scorers'|'first'|'totals'|'points'|'assists'|'other';chance:number|null;at:string|null;count:number|null;portrait:string|null;team:string|null;player:string|null};
export function hockeyBeforeSnapshot(){
 const event=atlas.events.find(e=>e.key==='nhl')!;
 const history=finalHistoryEvidence(finalHistoryWires.find(w=>w.key==='nhl')!).filter(p=>p.pregame);
 const props:BeforeProp[]=event.rows.map(row=>{
  const total=hockeyEvidence.points.find(p=>p.key===row.key),goal=scorerPregameEvidence.points.find(p=>p.key===row.key),first=firstScorerPregameEvidence.points.find(p=>p.key===row.key);
  const contribution=hockeyContribution(row,event.detail.id,'points','before')??hockeyContribution(row,event.detail.id,'assists','before');
  const observation=contribution?contribution.baseline:total?hockeyPregame(row):goal?scorerPregame(row):first?firstScorerPregame(row):null;
  const player=goal?.original;
  // Whitelist presentation data. Never pass final actuals, settlement, or terminal quotes to this view.
  return {key:row.key,title:row.outcome_name??row.market_name??'Original prop',market:row.market_name??'',source:row.source??'',marketID:row._market_id??null,contributors:row.contributor_outcome_ids??[],family:contribution?contribution.kind:total?'totals':goal?'scorers':first?'first':'other',chance:observation?.value??null,at:observation?.at??null,count:contribution?.threshold??total?.count??null,portrait:player?.player_headshot??null,team:player?.player_team??(contribution?row.player_team??null:null),player:contribution?.player??null};
 });
 return {eventID:15169793,start:hockeyEvidence.start,home:'Minnesota',away:'Boston',history,props};
}
export const hockeyBefore=hockeyBeforeSnapshot();
export function beforeLeaders(props:BeforeProp[],family:'scorers'|'first'){return props.filter(p=>p.family===family&&p.chance!==null).sort((a,b)=>b.chance!-a.chance!||a.title.localeCompare(b.title)).slice(0,6)}
export function beforeCatalog(props:BeforeProp[],family:string,page:number){const rows=props.filter(p=>family==='all'||p.family===family);const pages=Math.max(1,Math.ceil(rows.length/20));const safePage=Math.max(0,Math.min(pages-1,Math.floor(page)||0));return {rows:rows.slice(safePage*20,(safePage+1)*20),total:rows.length,pages,page:safePage};}
