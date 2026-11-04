import raw from './cricketFinalScore.json' with {type:'json'};
import {cricketEvent} from './cricketEvidence.ts';
export const cricketFinalWire=raw;
/** Cricket overs use balls after the dot, not decimal fractions of an over. */
export function cricketBalls(overs:string){const m=/^(\d+)\.([0-5])$/.exec(overs);return m?Number(m[1])*6+Number(m[2]):null;}
export function qualifiedCricketFinal(w=raw,event=cricketEvent){
 if(w.contract!=='cricket-final-state.v1'||w.marketEvent!==event||w.providerMatch!=='bcci:63f10afd-88ca-4501-a2a3-4e82105601cf'||w.home!=='India A'||w.away!=='Australia A'||w.status!=='final'||w.result!=='draw'||w.startDate!=='2026-09-29'||w.endDate!=='2026-10-02')return null;
 if(w.innings.length!==4||w.innings.some(i=>!Number.isInteger(i.runs)||i.runs<0||cricketBalls(i.overs)===null||i.wickets!==null&&(!Number.isInteger(i.wickets)||i.wickets<0||i.wickets>10)))return null;
 const [a,h,b,c]=w.innings;
 if(a.team!==w.away||a.number!==1||h.team!==w.home||h.number!==1||b.team!==w.away||b.number!==2||c.team!==w.home||c.number!==2||!b.declared||c.declared)return null;
 if(w.chase.team!==w.home||w.chase.runs!==c.runs||w.chase.wicketsLost!==c.wickets||w.chase.overs!==c.overs||w.chase.result!==w.result||w.chase.targetRuns!==a.runs+b.runs-h.runs+1||w.chase.runs>=w.chase.targetRuns||w.chase.wicketsLost>=10)return null;
 return w;
}
export const cricketFinal=qualifiedCricketFinal();
