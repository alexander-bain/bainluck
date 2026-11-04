/** Keep source identity and question scope; never infer venue equivalence from a title. */
export function groupCatalogRows<T extends {source:string;_market_id?:string|number;key?:string;market_name:string;category?:string;period?:unknown}>(rows:T[]):{key:string;rows:T[]}[]{
 const groups=new Map<string,T[]>();
 for(const [index,row] of rows.entries()){
  const key=JSON.stringify([row.source,row._market_id==null?['unidentified-row',row.key??index]:String(row._market_id),row.market_name,row.category||'other',row.period??null]);
  const group=groups.get(key);if(group)group.push(row);else groups.set(key,[row]);
 }
 return [...groups].map(([key,rows])=>({key,rows}));
}
