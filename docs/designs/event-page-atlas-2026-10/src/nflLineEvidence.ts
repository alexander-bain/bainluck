export type NFLDetailRow = {
 row_key:string;market_name:string;outcome_name:string;source:string;_market_id:number;
 pregame_mark?:unknown;_inverted?:unknown;observed_at?:unknown;
 over_probability?:unknown;probability?:unknown;actual?:unknown;hit?:unknown;
};
const chance=(v:unknown):number|null=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1?v:null;
/** The replay owns one post-game row capture. Admit its quote/result only at its
 * own observation time and a final match frame; a baseline is historical input,
 * not a timestamped point or a replacement for the opening/current quote. */
export function nflLineDetails(row:NFLDetailRow|undefined,at:string,final:boolean,conflict=false){
 if(!row)return null;
 const baseline=chance(row.pregame_mark);
 const pregame=baseline!==null&&typeof row._inverted==='boolean'?(row._inverted?1-baseline:baseline):null;
 const observed=typeof row.observed_at==='string'?Date.parse(row.observed_at):NaN;
 const cutoff=Date.parse(at);
 const admitted=final&&Number.isFinite(observed)&&Number.isFinite(cutoff)&&observed<=cutoff;
 const quote=admitted?chance(row.over_probability??row.probability):null;
 const actual=admitted&&!conflict&&typeof row.actual==='number'&&Number.isFinite(row.actual)&&row.actual>=0?row.actual:null;
 const result=admitted&&!conflict&&typeof row.hit==='boolean'?(row.hit?'Reached':'Not reached'):null;
 return {row,pregame,quote,quotedAt:quote!==null?row.observed_at as string:null,actual,result,admitted,conflict};
}
