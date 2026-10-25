/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { EntertainmentData, EntMarketRow } from "@/lib/api";

let payload: EntertainmentData;
let host: HTMLDivElement;
let mounted: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div"); document.body.appendChild(host);
  mounted = createRoot(host);
});
function renderPage() { act(() => mounted.render(<EntertainmentPage/>)); }
jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: payload }) }));
jest.mock("@/hooks", () => ({ usePageTracking: () => {}, useScrollDepth: () => {}, useEngagementTime: () => {} }));
jest.mock("@/lib/tmdb", () => ({ hasTMDBToken: () => false, searchMovie: async () => null, posterUrl: (p: string) => p }));
import EntertainmentPage from "@/app/entertainment/page";

function row(refused: boolean | undefined = true): EntMarketRow & { ladder_treatment_refused?: boolean } {
  return { q: "A threshold market", prob: 95, src: "kalshi", market_id: 4751,
    external_id: "KXRTTV-TEST", kind: "rt", outcome_count: 3,
    top_outcomes: [{name:"Above 30",prob:95,delta_24h:12},{name:"Above 20",prob:90,delta_24h:0},{name:"Above 10",prob:20,delta_24h:0}],
    volume_24h:null,resolution_date:null,image_url:null,hook:"Above 30 is 95% likely",ladder:true,
    headline:null,...(refused === undefined ? {} : {ladder_treatment_refused:refused}) };
}
function seed(subject = row(), grouped = false) {
  const good = {...row(false),market_id:4752,q:"Coherent sibling",prob:70,top_outcomes:[{name:"Above 10",prob:70,delta_24h:0},{name:"Above 20",prob:50,delta_24h:0},{name:"Above 30",prob:0,delta_24h:0}]};
  const groups = grouped ? [{title:"Coherent group",image_url:null,thresholds:[{label:"Above 40",prob:30,market_id:4752}]}] : [];
  payload = {total_markets:2,updated_at:"2026-10-25T00:00:00Z",trending:[subject,good],
    themes:{ music:{count:1,spotify_race:[subject],billboard_watch:[subject],billboard_groups:[],album_drops:[subject],artist_streaming:[subject],side_markets:[]},
      movies_tv:{count:2,rt_groups:groups,rt_markets:[subject,good],box_office_groups:[],box_office:[subject],reality_tv:[subject],side_markets:[]},
      tech_culture:{count:1,markets:[subject]}},cultural_moments:[subject],by_source:{kalshi:2,polymarket:0}} as EntertainmentData;
}
function subjectLinks() { return Array.from(host.querySelectorAll('a[href="/futures/4751"]')); }
function assertRefused() {
  expect(subjectLinks().length).toBeGreaterThanOrEqual(3);
  for(const link of subjectLinks()) {
    expect(link.textContent).toContain("A threshold market");
    expect(link.textContent).toContain("Prices unavailable");
    expect(link.textContent).not.toContain("%");
    expect(link.textContent).not.toContain("Above 30");
  }
}
afterEach(() => { act(() => mounted.unmount()); host.remove(); });
test.each([false,true])("refusal survives every mounted card and grouped RT layout=%s", grouped=>{
  seed(row(),grouped);renderPage();assertRefused();
  for(const label of ["Billboard","Album Drops","Artist Streaming","Spotify Race","Box Office","Reality TV","Rotten Tomatoes"]) {
    const button=Array.from(host.querySelectorAll("button")).find(b=>b.textContent===label);
    expect(button).toBeDefined();act(()=>button!.click());assertRefused();
  }
  expect(host.querySelector('a[href="/futures/4752"]')).not.toBeNull();
});
test.each([false,undefined])("explicit false and legacy missing flag retain their numeric behavior: %s", refused=>{
  const subject=row(false);if(refused===undefined)delete subject.ladder_treatment_refused;
  seed(subject);renderPage();
  expect(subjectLinks().some(a=>a.textContent?.includes("95%"))).toBe(true);
  expect(subjectLinks().some(a=>a.textContent?.includes("Prices unavailable"))).toBe(false);
});
