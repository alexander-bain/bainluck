interface IdleClock {set:(callback:()=>void,ms:number)=>unknown;clear:(handle:unknown)=>void}
const clock:IdleClock={set:(fn,ms)=>setTimeout(fn,ms),clear:handle=>clearTimeout(handle as ReturnType<typeof setTimeout>)};
/** Align only after free motion stops. A held drag can outlast the idle timer,
 * so release/cancel must arm it again even when the pointer no longer moves. */
export function attachReaderSettling(rail:HTMLElement,target:()=>number|null,idle:IdleClock=clock){
 let timer:unknown=null;
 const settle=()=>{timer=null;if(rail.dataset.dragging==='true')return;const left=target();if(left!==null&&Math.abs(rail.scrollLeft-left)>.5)rail.scrollTo({left,behavior:'instant'})};
 const schedule=()=>{if(timer!==null)idle.clear(timer);timer=idle.set(settle,140)};
 const events=['scroll','pointerup','pointercancel'] as const;
 for(const event of events)rail.addEventListener(event,schedule,{passive:true});
 return()=>{for(const event of events)rail.removeEventListener(event,schedule);if(timer!==null)idle.clear(timer)};
}
