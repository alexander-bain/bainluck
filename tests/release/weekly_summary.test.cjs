const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const file = path.resolve(__dirname,'../../frontend/e2e/helpers/weeklySummary.js');
test('summary records failure and incomplete evidence without claiming all clear',()=>{
  assert.ok(fs.existsSync(file),'weekly summary missing');
  const {summarize,weekStart} = require(file);
  assert.equal(weekStart('2026-11-01T07:00:00Z'),'2026-10-26');
  assert.throws(()=>summarize([]),/manifest/);
  assert.throws(()=>summarize([{run:{},journeys:[]}]),/manifest/);
  const result=summarize([{run:{observed_frontend_sha:'abc'},journeys:[{journey_id:'one',result:'infra_error',assertions:[]}]}]);
  assert.match(result,/incomplete/i);
  assert.doesNotMatch(result,/all clear/i);
});
