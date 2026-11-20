import {bindRequestLease,leaseKey,validatedBudgetDeadline} from './requestLease';
import {parseBlendPreview, readerAfter, readerAfterCommitFloor, type BlendPreviewReader} from './blendPreview';
// Test-only bounded current-state response reducer. Never changes observation time.
export function acceptCurrentPreview(reader: BlendPreviewReader, envelope: any, eventId: number, now: number, timing?: {requestStart: number}): BlendPreviewReader {
 const snapshot=envelope?.snapshot;
 if(!snapshot || snapshot.event_id!==eventId) return reader;
 let next=readerAfterCommitFloor(reader,envelope.control?.removal_rev);
 const snapshotFloor=snapshot.committed_floor;
 if(Number.isSafeInteger(snapshotFloor)&&snapshotFloor>=0)
   next=readerAfterCommitFloor(next,{[String(eventId)]:snapshotFloor});
 const epoch=snapshot.owner_epoch;
 if(!Number.isSafeInteger(epoch)||epoch<0||epoch<next.epoch)return next;
 if(epoch>next.epoch)next={...next,epoch,held:null,leaseCaps:{}};
 // An expired/empty authoritative response must still cap later live packets
 // from that same chain. It does not grant a new visible preview.
 if(timing && snapshot.lease_id!==undefined && snapshot.lease_id!==null && Number.isSafeInteger(snapshot.seq_floor) && snapshot.seq_floor>=0){
   const key=leaseKey({event_id:eventId,preview:{epoch,lease_id:snapshot.lease_id}});
   const deadline=validatedBudgetDeadline(timing.requestStart,now,snapshot.lease_remaining_ms);
   if(key!==null && deadline!==null){
     const caps=next.leaseCaps??{};
     if(!(key in caps)&&Object.keys(caps).length>=128)return {...next,held:null};
     const capped=Math.min(deadline,caps[key]??Infinity);
     const held=next.held?.leaseKey===key
       ? now>=capped?null:{...next.held,expiresAt:Math.min(next.held.expiresAt,capped)}
       : next.held;
     next={...next,held,leaseCaps:{...caps,[key]:capped}};
   }
 }
 const frame=parseBlendPreview(snapshot.frame);
 if(frame&&snapshot.lease_id!=null&&frame.preview.lease_id!==snapshot.lease_id)return next;
 if(frame && frame.preview.epoch===epoch) {
   const recovered={...frame,preview:{...frame.preview,recovered:true}};
   if(timing && recovered.preview.base_fold_revision)return next;
   if(timing && recovered.preview.kind==='blend' && !bindRequestLease(recovered,timing.requestStart,now,snapshot.lease_remaining_ms))return next;
   return readerAfter(next,recovered,eventId,now);
 }
 // A real known watermark is authority even when expired/commit-invalidated.
 const seq=snapshot.seq_floor,previous=next.singletonSequence;
 if(Number.isSafeInteger(seq)&&seq>=0&&(!previous||epoch>previous.epoch||seq>=previous.seq))
   next={...next,held:null,singletonSequence:{epoch,seq,kind:'unavailable',fingerprint:''}};
 return next;
}
