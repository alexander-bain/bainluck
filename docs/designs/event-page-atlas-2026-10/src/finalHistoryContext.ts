import headers from './finalHeaders.json' with {type:'json'};
import {halfWire} from './halfEvidence.ts';
import {finalHistoryWires} from './finalHistoryEvidence.ts';
export function finalHistoryContext(key:string){
 const wire=finalHistoryWires.find(w=>w.key===key);if(!wire)return null;
 if(key==='nba-half'&&wire.event_id===halfWire.eventID)return {home:wire.home_team,away:wire.away_team,homeScore:halfWire.homeFinal,awayScore:halfWire.awayFinal,unit:'points',baselineLabel:'Pregame',baselineAt:halfWire.winnerBaseline.timestamp,homeBaseline:halfWire.winnerBaseline.home_probability,awayBaseline:1-halfWire.winnerBaseline.home_probability};
 const h=headers.find(h=>h.id===key);if(!h||h.home!==wire.home_team||h.away!==wire.away_team)return null;
 return {home:h.home,away:h.away,homeScore:h.homeScore,awayScore:h.awayScore,unit:h.unit,baselineLabel:h.baselineLabel.startsWith('Opening')?'Pregame · opening':h.baselineLabel,baselineAt:h.baselineAt,homeBaseline:h.homeBaseline,awayBaseline:h.awayBaseline};
}
