/** UI behavior only; lifecycle and contract settlement come from separate producers. */
export function eventLifecycle(status:string):{label:string;withholdWinnerPrice:boolean;withholdProjection:boolean;message:string|null}{
 const halted:Record<string,string>={suspended:'Suspended',postponed:'Postponed',cancelled:'Cancelled',canceled:'Cancelled',voided:'Closed without a winner'};
 const label=halted[status];
 if(label)return {label,withholdWinnerPrice:true,withholdProjection:true,message:`Event ${label.toLowerCase()}. Original props and independently reported results remain available.`};
 return {label:status==='completed'?'Final':status==='live'?'In-game capture':status==='scheduled'?'Pregame capture':status==='field'?'Archived field':'Status unconfirmed',withholdWinnerPrice:!['completed','live','scheduled','field'].includes(status),withholdProjection:!['completed','live','scheduled'].includes(status),message:null};
}
