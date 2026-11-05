import {matchHistoryTarget} from './matchHistoryTarget.ts';
type Point={at:number;p:number;volume:number};
export type MatchInspectionRow={ticker:string;name:string;baseline:Point|null;points:Point[]};
export function matchInspectionSummary(rows:MatchInspectionRow[],at:number|null,baselineRows:MatchInspectionRow[]=rows){
 if(at!==null&&!Number.isSafeInteger(at))return [];
 return rows.map(row=>{
  const requested=at??row.points.reduce<number|null>((latest,p)=>Number.isSafeInteger(p.at)&&(latest===null||p.at>latest)?p.at:latest,null);
  const target=matchHistoryTarget(rows,row.ticker,requested),point=target===null?null:row.points.find(p=>p.at===target)??null;
  const baselineAt=matchHistoryTarget(baselineRows,row.ticker,row.baseline?.at),recordedBaseline=baselineAt===null?null:baselineRows.find(r=>r.ticker===row.ticker)?.points.find(p=>p.at===baselineAt)??null;
  const baseline=recordedBaseline&&recordedBaseline.p===row.baseline?.p?recordedBaseline:null;
  return {ticker:row.ticker,name:row.name,point,baseline};
 });
}
