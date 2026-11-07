/** A rounded archived quote must never claim impossible/certain unless the source is exactly 0/1. */
export function probabilityLabel(value:number|null|undefined):string {
 if(typeof value!=='number'||!Number.isFinite(value)||value<0||value>1)return 'Unavailable';
 if(value===0)return '0%';if(value===1)return '100%';
 const hundredths=Math.round(value*10000);
 if(hundredths===0)return '<0.01%';if(hundredths===10000)return '>99.99%';
 return `${hundredths/100}%`;
}
