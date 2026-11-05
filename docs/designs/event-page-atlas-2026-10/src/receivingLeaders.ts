import wire from './markets.json' with {type:'json'};
import flags from './finalCatalogFlags.json' with {type:'json'};
import rules from './receivingLeaderRules.json' with {type:'json'};
import {nflOriginalBaseline} from './nflOriginalBaseline.ts';
export type LeaderRow=(typeof wire)[number];
export const receivingLeaderID='leader:receiving' as const,receivingLeaderMarket=62733986;
const definitions=[{key:'player_props:331',name:'Kalif Raymond',short:'Raymond'},{key:'player_props:332',name:'DeVonta Smith',short:'Smith'},{key:'player_props:333',name:'Colston Loveland',short:'Loveland'},{key:'player_props:334',name:'Rome Odunze',short:'Odunze'},{key:'player_props:335',name:'Saquon Barkley',short:'Barkley'},{key:'player_props:336',name:"D'Andre Swift",short:'Swift'},{key:'player_props:337',name:'Dontayvion Wicks',short:'Wicks'},{key:'player_props:338',name:'Makai Lemon',short:'Lemon'},{key:'player_props:339',name:'Luther Burden III',short:'Burden III'}];
export const leaderKnownKey=(key:string)=>definitions.some(d=>d.key===key);
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
export const leaderCents=(p:number|null)=>p===null?'Unavailable':`${Number((p*100).toFixed(1))}¢`;
export function leaderOwns(row:LeaderRow){const d=definitions.find(d=>d.key===row.row_key);return !!d&&row._market_id===receivingLeaderMarket&&row.source==='kalshi'&&row.market_name==='Philadelphia vs Chicago: Most Receiving Yards'&&row.outcome_name===d.name&&row.category==='player_props'&&row.threshold==null&&row.period==null&&row._inverted===false}
export function leaderResult(row:LeaderRow,phase:string){if(phase!=='Final')return null;return flags[row.row_key as keyof typeof flags]!==true&&(row as LeaderRow&{result_unconfirmed?:boolean}).result_unconfirmed!==true&&row.resolution_source==='api_settlement'&&typeof row.is_winner==='boolean'?(row.is_winner?'Recorded winner':'Not the recorded winner'):'Result unconfirmed'}
export function leaderYards(name:string,phase:string,rows:readonly LeaderRow[]=wire){
 if(phase!=='Final')return null;
 const originals=rows.filter(r=>r._market_id===62146482&&typeof r.outcome_name==='string'&&r.outcome_name.startsWith(name+': '));
 if(!originals.length||new Set(originals.map(r=>r.row_key)).size!==originals.length||originals.some(r=>r.source!=='kalshi'||r.market_name!=='Philadelphia vs Chicago: Receiving Yards'||r.category!=='player_props'||r._inverted!==false||r.period!=null||!finite(r.threshold)||!Number.isSafeInteger(r.threshold)||r.outcome_name!==name+': '+r.threshold+'+'))return null;
 const first=originals[0],actual=first.actual;
 return finite(actual)&&Number.isSafeInteger(actual)&&originals.every(r=>r.actual===actual&&r.observed_at===first.observed_at)?actual:null;
}
export function receivingLeaders(phase:string,rows:readonly LeaderRow[]=wire,eventID=14780549){
 if(eventID!==rules.eventID||!['Before','During','Final'].includes(phase))return null;
 if(rows.filter(r=>r._market_id===receivingLeaderMarket).length!==9)return null;
 const outcomes=definitions.map(d=>{const matches=rows.filter(r=>r.row_key===d.key);if(matches.length!==1||!leaderOwns(matches[0]))return null;const row=matches[0];return {...d,row,price:nflOriginalBaseline(row).value,result:leaderResult(row,phase),actual:leaderYards(d.name,phase,rows),observedAt:phase==='Final'?row.observed_at:null}});
 if(outcomes.some(p=>p===null))return null;
 return outcomes.filter(p=>p!==null).sort((a,b)=>(b.price??-1)-(a.price??-1)||a.name.localeCompare(b.name));
}
export function receivingLeaderDefault(phase:string){const rows=receivingLeaders(phase);if(!rows?.length)return null;const winners=rows.filter(p=>p.result==='Recorded winner');return phase==='Final'&&winners.length===1?winners[0].key:rows[0].key}
export function receivingLeaderStory(phase:string){const rows=receivingLeaders(phase);return rows?{id:receivingLeaderID,family:'leader' as const,name:'Receiving-yard leaders',score:null,originals:rows.map(p=>p.key)}:null}
