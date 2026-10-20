import { applyLiveFrameRail, type LiveFrame } from '../../lib/eventLivePush';
const stamp='2026-10-19T22:00:00Z';
const entry={value:.6,updated_at:stamp};
const page={id:1,status:'live',hero_probability_source:'blend',hero_probability:.6,hero_probability_observed_at:stamp,blend_fold_revision:{'1':10},win_probability_sources:{polymarket:entry}};
const frame=():LiveFrame => ({event_id:1,p:.65,source:'kalshi',source_value:.7,status:'live',updated_at:stamp,rev:{'1':11},source_snapshot:{event_id:1,rev:{'1':11},win_probability_sources:{polymarket:entry,kalshi:entry}}});
it('only a newly adopted probability-source membership asks history',()=>{
 const f=frame();const result=applyLiveFrameRail(page,f);
 expect(result.sourceAdded).toBe(true);expect(result.snapshotRail).toBe(true);
 const newer={...f,rev:{'1':12},source_snapshot:{event_id:1,rev:{'1':12},win_probability_sources:{polymarket:entry,kalshi:{...entry,value:.71}}}};
 expect(applyLiveFrameRail(result.next,newer).sourceAdded).toBeUndefined();
});
it.each(['legacy','stale','malformed','foreign','unpriced','unknown','terminal'])('%s does not trigger a new-source read',damage=>{
 const f=frame();let held=page;
 if(damage==='legacy') delete f.source_snapshot;
 if(damage==='stale'){f.rev={'1':9};(f.source_snapshot as any).rev={'1':9};}
 if(damage==='malformed')(f.source_snapshot as any).rev={'1':12};
 if(damage==='foreign')(f.source_snapshot as any).event_id=2;
 if(damage==='unpriced')(f.source_snapshot as any).win_probability_sources={};
 if(damage==='unknown')(f.source_snapshot as any).win_probability_sources={polymarket:entry,unknown_source:entry};
 if(damage==='terminal')held={...page,status:'completed'};
 expect(applyLiveFrameRail(held,f).sourceAdded).toBeUndefined();
});
