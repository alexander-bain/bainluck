import {useEffect,useMemo,useState} from 'react';
import {receiveCatalogSnapshot,type CatalogSession,type SessionRow} from './catalogPageSession';
/** Mount above layout, tabs, search and pagination. A new pageKey explicitly starts a fresh page. */
export function useCatalogPageSession<T extends SessionRow>(eventID:string,status:string,qualityHold:boolean,rows:T[],pageKey=eventID){
 const snapshot=useMemo(()=>({eventID,status,qualityHold,rows}),[eventID,status,qualityHold,rows]);
 const [received,setReceived]=useState<{pageKey:string;session:CatalogSession<T>}>(()=>({pageKey,session:receiveCatalogSnapshot(null,snapshot)}));
 const session=useMemo(()=>receiveCatalogSnapshot(received.pageKey===pageKey?received.session:null,snapshot),[received,snapshot,pageKey]);
 useEffect(()=>{if(received.pageKey!==pageKey||received.session!==session)setReceived({pageKey,session})},[received,session,pageKey]);
 return session;
}
