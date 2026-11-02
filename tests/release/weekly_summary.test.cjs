const {test} = require('node:test');
const assert = require('node:assert/strict');
const {buildRunManifest}=require('../../frontend/e2e/helpers/manifest');
const {summarize,weekStart}=require('../../frontend/e2e/helpers/weeklySummary');
const sha='1'.repeat(40);
const expected={headSha:sha,runId:'1234'};
function manifest(result='pass') {
  const record={journey_id:'discover.landing',project:'desktop',viewport:{width:1440,height:900},url_path:'/',redirect_chain:[],
    selected_fixture_ids:[],started_at_utc:'2026-07-31T19:00:00Z',finished_at_utc:'2026-07-31T19:00:12Z',duration_ms:12000,
    assertions:[{assertion_id:'content.real_card_or_named_empty',ok:result==='pass',detail:null}],checked_clean:[],console_errors:[],
    page_errors:[],failed_requests:[],telemetry_requests:[],first_card_ms:900,
    artifacts:result==='infra_error'?[]:[{name:'terminal.png',path:'artifacts/terminal.png',sha256:'c'.repeat(64),bytes:1024}],attempt:1,result};
  return buildRunManifest({runId:'1234',runUrl:'https://github.com/alexander-bain/bainluck/actions/runs/1234',pack:'deploy-smoke',
    trigger:'schedule',startedAt:'2026-07-31T19:00:00Z',finishedAt:'2026-07-31T19:01:00Z',requestedFrontendSha:sha,
    observedFrontendSha:sha,checkoutSha:sha,runnerStatus:result==='pass'?'passed':'failed',observedBackendSha:'deadbeef',
    baseUrl:'https://www.bainluck.com',apiBaseUrl:'https://api.bainluck.com',runtime:{node:'v20.11.0',playwright:'1.48.2',browser:'chromium-1140',os:'linux-x64'},
    selectedCount:1,journeys:[record]});
}
test('summary records incomplete evidence and refuses empty or untrusted manifests',()=>{
  assert.equal(weekStart('2026-11-01T07:00:00Z'),'2026-10-26');
  assert.throws(()=>summarize([],expected),/manifest/);
  assert.throws(()=>summarize([{run:{},journeys:[]}],expected),/manifest/);
  const result=summarize([manifest('infra_error')],expected);
  assert.match(result,/incomplete/i);assert.doesNotMatch(result,/all clear/i);
});
test('summary rejects false pass, foreign grading commit and mismatched run identity',()=>{
  const contradictory=manifest();contradictory.journeys[0].assertions[0].ok=false;
  assert.throws(()=>summarize([contradictory],expected),/manifest/);
  assert.throws(()=>summarize([manifest()],{...expected,headSha:'2'.repeat(40)}),/grading commit/);
  assert.throws(()=>summarize([manifest()],{...expected,runId:'other'}),/run identity/);
  assert.match(summarize([manifest()],expected),/pass/);
});
