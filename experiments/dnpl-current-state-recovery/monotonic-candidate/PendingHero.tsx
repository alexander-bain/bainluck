import React from 'react';
import ActualHero from '../source/frontend/components/EventHeroProbabilityPair';
export default function PendingHero(props:any){
 const {recoveryPending,...rest}=props;
 return recoveryPending ? <div role="status" data-current-preview-pending={recoveryPending} aria-live="polite" style={{fontSize:16,fontWeight:600,textAlign:'center',minHeight:58,display:'flex',alignItems:'center',justifyContent:'center'}}>{recoveryPending==='pending'?'Checking current probability…':'Current probability unavailable'}</div> : <ActualHero {...rest}/>;
}
