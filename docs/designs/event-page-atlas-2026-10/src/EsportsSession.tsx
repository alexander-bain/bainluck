import {createContext,useContext,useState,type ReactNode,type Dispatch,type SetStateAction} from 'react';
import type {EsportsFamily} from './esportsFocus';
import type {EsportsRow} from './esportsEvidence';
import type {CatalogAnchor} from './catalogSelection';
type Session={activeCard:string|null;setActiveCard:Dispatch<SetStateAction<string|null>>;focus:EsportsFamily|null;setFocus:Dispatch<SetStateAction<EsportsFamily|null>>;anchors:Record<string,CatalogAnchor<EsportsRow>>;setAnchors:Dispatch<SetStateAction<Record<string,CatalogAnchor<EsportsRow>>>>};
const SessionContext=createContext<Session|null>(null);
export function EsportsSessionProvider({children}:{children:ReactNode}){
 const [activeCard,setActiveCard]=useState<string|null>(null);const [focus,setFocus]=useState<EsportsFamily|null>(null),[anchors,setAnchors]=useState<Record<string,CatalogAnchor<EsportsRow>>>({});
 return <SessionContext.Provider value={{activeCard,setActiveCard,focus,setFocus,anchors,setAnchors}}>{children}</SessionContext.Provider>;
}
export function useEsportsSession(){const value=useContext(SessionContext);if(!value)throw new Error('Esports session provider missing');return value;}
