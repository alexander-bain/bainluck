import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { writeFileSync } from "fs";
import { join } from "path";
jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true, useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("recharts", () => ({
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
    React.cloneElement(children, { width: 390, height: 300 }),
}));
import OddsChart from "@/components/OddsChart";
import type { WinProbHistoryPoint } from "@/lib/types";
const point = (time: string, p: number | null): WinProbHistoryPoint => ({
  timestamp: `2026-10-19T11:${time}Z`, home_probability:p,
  away_probability:p === null ? null : 1-p, draw_probability:null,
  ...(p === null ? {game_state:{live_source_withdrawal:true}} : {}),
});
const base = [point("39:00",.60),point("40:00",.60),point("41:27",.60)];
const tail = [...base,point("41:55.279",.78),point("41:55.940",null)];
function chart(points: WinProbHistoryPoint[], extra: Record<string, unknown> = {}) {
 return renderToStaticMarkup(<OddsChart history={[]} homeTeam="76ers" awayTeam="Celtics"
  winProbHistory={{polymarket:points}} winProbSources={{polymarket:{display_name:"Polymarket",color:"#3b82f6",type:"market",snapshot_count:points.length}}}
  isLive eventStatus="live" externalTimeRange="live" commenceTime="2026-10-19T11:38:00Z"
  chartStartTime="2026-10-19T11:39:00Z" chartEndTime="2026-10-19T11:44:00Z" {...extra}/>);
}
function path(html: string, color = "#3b82f6") {
 const tags=html.match(/<path[^>]*recharts-line-curve[^>]*>/g) ?? [];
 return tags.filter(t => t.includes(`stroke="${color}"`) && !t.includes('stroke-dasharray="2 5"'))
  .map(t=> / d="([^"]*)"/.exec(t)?.[1] ?? '').join('');
}
function endX(d: string) {
 const pairs=d.match(/-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?/g) ?? [];
 return Number(pairs.at(-1)?.split(',')[0]);
}
const callout=(html:string)=> /data-callout-label="([^"]+)"/.exec(html)?.[1];
describe('11272 explicit withdrawal is not a missing minute',()=>{
 test.each([undefined, "true", false])('ordinary null marker %s retains parent live carry',marker=>{
  const unmarked=point("41:55.940",null);
  unmarked.game_state=marker===undefined?undefined:{live_source_withdrawal:marker};
  const html=chart([...base,point("41:55.279",.78),unmarked]);
  expect(callout(html)).toBe('60%');
  expect(endX(path(html))).toBeGreaterThan(370);
 });
 test.each([undefined, "true"])('ordinary null marker %s retains finished carry',marker=>{
  const unmarked=point("41:55.940",null);
  unmarked.game_state=marker===undefined?undefined:{live_source_withdrawal:marker};
  const html=chart([...base,point("41:55.279",.78),unmarked],{isLive:false,eventStatus:"finished"});
  expect(callout(html)).toBe('60%');
  expect(endX(path(html))).toBeGreaterThan(370);
 });
 test('an ordinary same-minute null cannot erase a marked withdrawal price',()=>{
  const unmarked=point("41:56",null);unmarked.game_state=undefined;
  const html=chart([...tail,unmarked]);
  expect(callout(html)).toBe('78%');
  expect(path(html)).toBe(path(chart(tail)));
 });
 test('an ordinary null after withdrawal cannot resume carry',()=>{
  const unmarked=point("42:20",null);unmarked.game_state=undefined;
  const html=chart([...tail,unmarked]);
  expect(callout(html)).toBe('78%');
  expect(endX(path(html))).toBe(endX(path(chart(tail))));
 });

 test('a marked production withdrawal tail keeps78 and stops before the next minute',()=>{
  const html=chart(tail), healthy=chart([...base,point("41:55.279",.78)]);
  if(process.env.LAB_RESULTS_DIR) writeFileSync(join(process.env.LAB_RESULTS_DIR,'chart.html'),html);
  expect(callout(html)).toBe('78%');
  expect(endX(path(html))).toBeLessThan(endX(path(healthy)));
  expect(path(html)).not.toBe(path(chart(base)));
 });
 test('quiet time still carries the latest real reading',()=>{
  const html=chart([...base,point("41:55.279",.78)]);
  expect(callout(html)).toBe('78%');
  expect(endX(path(html))).toBeGreaterThan(370);
 });
 test('a withdrawal in a later empty minute never fills itself from the earlier price',()=>{
  const before=[...base,point("41:55.279",.78)];
  const html=chart([...before,point("42:20",null)]);
  expect(callout(html)).toBe('78%');
  expect(endX(path(html))).toBe(endX(path(chart(tail))));
 });
 test('a later real re-addition resumes after the withdrawn interval without bridging',()=>{
  const html=chart([...tail,point("43:00",.72)]);
  expect(callout(html)).toBe('72%');
  expect((path(html).match(/M/g)??[]).length).toBe(2);
 });
 test('a newer price in the withdrawal minute restores the current quote',()=>{
  const html=chart([...tail,point("41:58",.72)]);
  expect(callout(html)).toBe('72%');
  expect(endX(path(html))).toBeGreaterThan(370);
 });
 test('withdrawal of one source does not stop the other',()=>{
  const sibling=[point("39:00",.55),point("41:50",.56)];
  const html=chart(tail,{winProbHistory:{polymarket:tail,kalshi:sibling},winProbSources:{
   polymarket:{display_name:"Polymarket",color:"#3b82f6",type:"market",snapshot_count:tail.length},
   kalshi:{display_name:"Kalshi",color:"#22c55e",type:"market",snapshot_count:sibling.length}}});
  expect(endX(path(html))).toBeLessThan(endX(path(html,'#22c55e')));
 });
});
