import { createReconnectCatchup } from '@/lib/reconnectCatchup';

test('prompt jitter spreads all4900 ordinary draws across100–250ms without a synchronized cap',()=>{
 jest.useFakeTimers();jest.setSystemTime(0);
 try {
  const bins=new Map<number,number>();
  for(let draw=100;draw<=4999;draw++) {
   const start=Date.now();let fired:number|undefined;
   const c=createReconnectCatchup(()=>{fired=Date.now()-start;},()=>draw);
   c.recover(1,250);jest.runOnlyPendingTimers();c.cancel();
   expect(fired).toBeDefined();expect(fired!).toBeGreaterThanOrEqual(100);expect(fired!).toBeLessThanOrEqual(250);
   bins.set(fired!,(bins.get(fired!)??0)+1);
  }
  expect(bins.size).toBe(151);expect(Math.max(...bins.values())).toBeLessThanOrEqual(33);
 } finally {jest.useRealTimers();}
});
