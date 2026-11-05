// The existing four source-backed families; expansion never synthesizes a new combination.
export const tennisFocusCards=[
 {id:'exact',name:'Exact set finishes',outcomeIDs:[245059339,245059341,245059340,245059338]},
 {id:'set',name:'First-set expectations',outcomeIDs:[245152775,245152776]},
 {id:'totals',name:'Total-game milestones',outcomeIDs:[245152784,245152786]},
 {id:'handicaps',name:'Set and game handicaps',outcomeIDs:[245152788,245201950]}
] as const;
export type TennisFocusKind=typeof tennisFocusCards[number]['id'];
