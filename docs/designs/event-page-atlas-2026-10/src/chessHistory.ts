import raw from './chessHistory.json' with {type:'json'};
export type ChessPoint={timestamp:string;probability:number};
export type ChessContender={outcome_id:number;name:string;history:ChessPoint[]};
export const chessContenders=raw.outcomes as ChessContender[];
export const chessCapture={marketId:raw.market_id,title:raw.market_name,from:raw.coverage_start,through:raw.coverage_end};
export const chessGapMs=36*60*60*1000;
export function chessContender(id:number){return chessContenders.find(o=>o.outcome_id===id)??chessContenders[0]}
export function chessSelection(contender:ChessContender,at:string|null){const found=contender.history.findIndex(p=>p.timestamp===at);const index=found<0?contender.history.length-1:found;return {point:contender.history[index],index,inspecting:found>=0}}
export function chessComparison(id:number){return chessContender(id===235705516?235705515:235705516)}
export function chessSegments(contender:ChessContender){const segments:ChessPoint[][]=[];for(const point of contender.history){const last=segments.at(-1)?.at(-1);if(last&&Date.parse(point.timestamp)-Date.parse(last.timestamp)<=chessGapMs)segments.at(-1)!.push(point);else segments.push([point])}return segments}
export function chessPlot(contender:ChessContender){return chessSegments(contender).flatMap((segment,i)=>[...(i?[{time:Date.parse(segment[0].timestamp)-1,chance:null}]:[]),...segment.map(p=>({time:Date.parse(p.timestamp),chance:p.probability*100}))])}
export function chessAt(contender:ChessContender,at:string){return contender.history.find(p=>p.timestamp===at)??null}
export function chessScale(contenders:ChessContender[],full:boolean){return full?100:Math.max(10,Math.ceil(Math.max(...contenders.flatMap(o=>o.history.map(p=>p.probability*100)))/10)*10)}
