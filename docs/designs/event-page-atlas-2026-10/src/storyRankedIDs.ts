/** Keep the finite renderer bank separate from a service/editorial ranking. */
export function storyRankedIDs(known:readonly string[],incoming:unknown=undefined):string[]{
 const bank=[...new Set(known.filter(id=>typeof id==='string'&&id.length>0))];
 if(incoming===undefined||!Array.isArray(incoming))return bank;
 if(incoming.length===0)return [];
 const order=[...new Set(incoming.filter((id):id is string=>typeof id==='string'&&bank.includes(id)))];
 return order.length?order:bank;
}
