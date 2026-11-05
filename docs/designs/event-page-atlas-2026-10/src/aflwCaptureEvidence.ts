import {officialAflwFinal} from './aflwFinalScore.ts';
import captures from './aflwCaptures.json' with {type:'json'};
const adapt=(payload:typeof captures.earlier|typeof captures.latest,file:string)=>payload.other.map((row,index)=>({...row,key:`${file}:${index}`,source_file:file,category:'other'}));
const event=(payload:typeof captures.earlier|typeof captures.latest,file:string)=>({key:'aflw-refresh',label:'AFLW · retained props',unit:'points',source:'polymarket',detail:{...payload,id:payload.event_id,sport_name:"AFL Women's"},rows:adapt(payload,file),series:[],pregame_projection:null});
export const earlierAflw=event(captures.earlier,'aflw-earlier-game-markets.json');
export const latestAflw=event(captures.latest,'aflw-15324784-game-markets.json');
export {captures as aflwCaptures};

// A separate design view combines independently sourced final actuals with retained original contracts.
export const finalAflw=officialAflwFinal?{...earlierAflw,detail:{...captures.latestDetail,status:'completed',home_score:officialAflwFinal.homeScore,away_score:officialAflwFinal.awayScore},rows:[...earlierAflw.rows]}:latestAflw;
