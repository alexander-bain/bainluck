import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
let marketPayload: unknown;
const streamRead = jest.fn(() => ({ data: marketPayload, connected: false }));
jest.mock("@/hooks/useGameMarketsStream", () => ({ useGameMarketsStream: () => streamRead() }));
jest.mock("next/dynamic", () => ({ __esModule: true, default: (loader: () => unknown) => {
 const name=loader.toString(); return function Marker(){return name.includes("DuringPlayerPropsMatrix") ? <div>During matrix mounted</div> : name.includes("PlayerPropsDashboard") ? <div>Legacy dashboard mounted</div> : null;};
}}));
let eventPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const isEvent = Array.isArray(key) && key[0] === "event";
    return {
      data: isEvent ? eventPayload : undefined,
      error: undefined,
      isLoading: false,
      mutate: () => undefined,
    };
  },
}));

jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({
    isPinned: () => false,
    togglePin: () => undefined,
    isMaxReached: false,
  }),
}));

// Not connected, so the page is on the POLL branch — which is the branch that
// draws the ring. A pushed page shows its age stamp instead (live/034 S2).
jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15310172",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15310172" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15310172" } }),
    ),
  );
}


const data={contract:"10236.v1",stats:[{stat_key:"hits",period_key:"full_game",predicate:"count_at_least"}],rows:[{question_key:"q",stat_key:"hits",subject:{key:"p",label:"Player",kind:"player"},period_key:"full_game",predicate:{kind:"count_at_least",count:1,side:"over",label:"1+"},complement_question_key:null,current:{state:"quoted",probability:.4}}]};
beforeEach(()=>{streamRead.mockClear();eventPayload={id:15310172,status:"live",home_team:"Home",away_team:"Away",sport_key:"baseball_mlb",commence_time:"2026-10-03T00:00:00Z",win_probability_sources:{}}; marketPayload={event_id:15310172,player_props:[],totals:[],spreads:[],matchups:[],other:[],during_player_props:data};});
it("mounts typed rows with empty legacy props via one existing stream",()=>{expect(draw()).toContain("During matrix mounted");expect(streamRead).toHaveBeenCalledTimes(1);});
it.each(["scheduled","null","unsupported","empty","other-event"])("keeps %s out while preserving legacy props",mode=>{
 if(mode==="scheduled")eventPayload={...eventPayload as object,status:"scheduled"};
 marketPayload={...marketPayload as object,player_props:[{player_name:"Legacy Player",market_name:"Hits",outcomes:[]}],during_player_props:mode==="null"?null:mode==="unsupported"?{...data,contract:"other"}:mode==="empty"?{...data,rows:[]}:data,event_id:mode==="other-event"?99:15310172};
 const html=draw();expect(html).not.toContain("During matrix mounted");expect(html).toContain("Legacy dashboard mounted");expect(html).toContain("All 1 prop");});
