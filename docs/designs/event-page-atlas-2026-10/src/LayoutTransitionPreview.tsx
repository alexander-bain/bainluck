import {useEffect,useRef,useState} from 'react';
/** External preview control: exercise layout remount without clicking outside a modal. */
export function LayoutTransitionPreview({onSwitch}:{onSwitch:()=>void}){
 const latest=useRef(onSwitch);latest.current=onSwitch;
 const timer=useRef<ReturnType<typeof setTimeout>|null>(null),[pending,setPending]=useState(false);
 useEffect(()=>()=>{if(timer.current)clearTimeout(timer.current)},[]);
 const toggle=()=>{if(timer.current){clearTimeout(timer.current);timer.current=null;setPending(false);return}
  setPending(true);timer.current=setTimeout(()=>{timer.current=null;setPending(false);latest.current()},4000)};
 return <details className="sr-arrival-controls"><summary>Layout checks</summary><div><span>Preview only · keeps an open reader open during layout reconstruction.</span><button onClick={toggle}>{pending?'Cancel scheduled layout change':'Switch layout in 4 seconds'}</button></div></details>;
}
