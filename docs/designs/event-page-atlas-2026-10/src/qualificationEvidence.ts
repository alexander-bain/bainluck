import capture from './qualification-capture.json' with {type:'json'};
export type QualificationCapture=typeof capture;
export function qualificationNoTrades(c:QualificationCapture):boolean {
 return c.event==='KXSOLAXQUAL-28'&&c.mutuallyExclusive===false&&c.historyPoints===0&&c.teams.length===46&&new Set(c.teams.map(t=>t.id)).size===46&&c.teams.every(t=>t.id===t.sourceRecord.ticker&&t.sourceRecord.event_ticker===c.event&&t.name===t.sourceRecord.yes_sub_title&&t.predicate===t.sourceRecord.title&&t.rules===t.sourceRecord.rules_primary&&t.sourceRecord.status==='active'&&t.sourceRecord.result===''&&t.sourceRecord.volume_fp==='0.00'&&t.sourceRecord.last_price_dollars==='0.0000');
}
export const qualificationCapture=capture;
export const qualificationTeams=[...capture.teams].sort((a,b)=>a.name.localeCompare(b.name,'en'));
