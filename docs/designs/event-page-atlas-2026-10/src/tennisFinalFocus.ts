// Only the four source-backed families from this exact completed match.
export const tennisFinalCards=[
 {id:'sets',name:'Set winners'},
 {id:'totals',name:'Total games'},
 {id:'exact',name:'Exact set finishes'},
 {id:'handicaps',name:'Set and game handicaps'}
] as const;
export type TennisFinalKind=typeof tennisFinalCards[number]['id'];
