import {skatingOutcomeHistory} from './skatingOutcomeHistory.ts';
import {skatingGrade,skatingResult,type SkatePhase} from './skatingEvidence.ts';
import {probabilityLabel} from './probabilityLabel.ts';

export function skatingPropDetail(id:string,side:string,phase:SkatePhase) {
  const history=skatingOutcomeHistory(id,side,phase);
  if(!history)return null;
  const start=phase==='before'?(history.points[0]??null):history.baseline;
  const end=history.points.at(-1)??null;
  const single=start!==null&&start===end;
  const move=start&&end&&!single?end.p-start.p:null;
  const grade=skatingGrade(history.market,phase,side);
  const result=history.market.resultID?skatingResult(history.market.resultID,phase):null;
  return {...history,start,end,move,single,
    startLabel:phase==='before'?'First captured trade':'Before race day',
    endLabel:phase==='before'?(single?'Before race day · only captured trade':'Before race day'):(single?'Before race day · last recorded':'Last recorded trade'),
    grade:grade==='Won'?'Happened':grade==='Lost'?'Didn’t happen':grade,
    result};
}

export function skatingMoveLabel(move:number|null) {
  if(move===null)return 'Comparison unavailable';
  if(move===0)return 'Same recorded chance at both times';
  return probabilityLabel(Math.abs(move)).replace('%','')+' points '+(move>0?'higher':'lower');
}
