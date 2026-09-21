import { readFileSync } from "fs";
import { join } from "path";
import { MAX_LIVE_CHART_FRAMES, rememberLiveChartFrame, mergeLiveChartHistory, type LiveChartPoint } from "@/lib/liveChartHistory";
import type { LiveStreamFrame } from "@/lib/liveStreamController";

const t = (s: number) => new Date(Date.UTC(2026, 8, 21, 20, 0, s)).toISOString();
const frame = (s: number, p: number | null = .6, extra = {}): LiveStreamFrame => ({
  event_id: 42, p, source: "kalshi", source_value: .65,
  updated_at: t(s), status: "live", ...extra,
});
const history = { aggregate_line: [{ timestamp: t(0), home_probability: .5 }], score_history: [{ home_score: 1 }], blend_edge_pinned: true };

describe("#920 actual published observations reach the main chart", () => {
  it("advances the time axis without rewriting the past or plotting the raw source", () => {
    const points = rememberLiveChartFrame([], frame(5), 42);
    const result = mergeLiveChartHistory(history, points)!;
    expect(result.aggregate_line).toEqual([...history.aggregate_line, { timestamp: t(5), home_probability: .6 }]);
    expect(history.aggregate_line[0].home_probability).toBe(.5);
    expect(result.score_history).toBe(history.score_history);
  });
  it("retains a real sudden move and reversal through the next poll", () => {
    let points: LiveChartPoint[] = [];
    for (const [s, p] of [[5,.6],[10,.9],[15,.6]]) points = rememberLiveChartFrame(points, frame(s,p),42);
    const result = mergeLiveChartHistory({ aggregate_line: [...history.aggregate_line, { timestamp:t(20), home_probability:.61 }] },points)!;
    expect(result.aggregate_line.map(p=>p.home_probability)).toEqual([.5,.6,.9,.6,.61]);
    expect(result.aggregate_line.map(p=>p.timestamp)).toEqual([0,5,10,15,20].map(t));
  });
  it("keeps distinct unchanged observations and zero; invents no in-between points", () => {
    const points = rememberLiveChartFrame(rememberLiveChartFrame([],frame(5,0),42),frame(55,0),42);
    expect(points).toEqual([{timestamp:t(5),home_probability:0},{timestamp:t(55),home_probability:0}]);
  });
  it("sorts late observations without duplicate timestamps and preserves persisted values on overlap", () => {
    let points = rememberLiveChartFrame([],frame(15,.7),42);
    points = rememberLiveChartFrame(points,frame(5,.6),42);
    points = rememberLiveChartFrame(points,frame(15,.7),42);
    expect(points).toHaveLength(2);
    const result=mergeLiveChartHistory({aggregate_line:[{timestamp:t(15),home_probability:.71}]},points)!;
    expect(result.aggregate_line).toEqual([{timestamp:t(5),home_probability:.6},{timestamp:t(15),home_probability:.71}]);
  });
  it.each([
    frame(5,null),frame(5,NaN),frame(5,Infinity),frame(5,-.1),frame(5,1.1),
    frame(5,.6,{event_id:43}),frame(5,.6,{updated_at:"broken"}),frame(5,.6,{status:"completed"}),
  ])("rejects invalid, foreign or terminal frames %#", f=>{
    const points: LiveChartPoint[]=[];
    expect(rememberLiveChartFrame(points,f,42)).toBe(points);
  });
  it("bounds memory by latest observation time, not packet arrival order", () => {
    let points:LiveChartPoint[]=[];
    for(let i=0;i<MAX_LIVE_CHART_FRAMES+10;i++) points=rememberLiveChartFrame(points,frame(i),42);
    expect(points).toHaveLength(MAX_LIVE_CHART_FRAMES);
    expect(points[0].timestamp).toBe(t(10));
    expect(rememberLiveChartFrame(points,frame(0),42)).toEqual(points);
  });
  it("leaves unloaded and quiet pages unchanged",()=>{
    expect(mergeLiveChartHistory(undefined,rememberLiveChartFrame([],frame(5),42))).toBeUndefined();
    expect(mergeLiveChartHistory(history,[])).toBe(history);
  });
  it("does not mutate a frozen response or a frozen buffer",()=>{
    const base=Object.freeze({aggregate_line:Object.freeze(history.aggregate_line)}) as unknown as typeof history;
    const points=Object.freeze([{timestamp:t(5),home_probability:.6}]) as unknown as LiveChartPoint[];
    expect(mergeLiveChartHistory(base,points)!.aggregate_line).toHaveLength(2);
  });
  it("wires the shared history into both the main chart and expanded chart",()=>{
    const page=readFileSync(join(process.cwd(),"app/events/[id]/page.tsx"),"utf8");
    const hook=readFileSync(join(process.cwd(),"hooks/useLiveEventStream.ts"),"utf8");
    expect(page).toContain("mergeLiveChartHistory(servedHistory, isLive ? chartPoints : [])");
    expect(page.match(/aggregateLine=\{historyData\?\.aggregate_line \?\? undefined\}/g)).toHaveLength(2);
    expect(hook).toContain("rememberLiveChartFrame");
    expect(hook).toContain("chartEventId === eventId");
  });
});
