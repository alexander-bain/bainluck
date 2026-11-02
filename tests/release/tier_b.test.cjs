const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const file = path.resolve(__dirname, '../../tools/release/tier_b.cjs');
test('Tier-B rejects self-approval and accepts current-head independent approval', () => {
  assert.ok(fs.existsSync(file), 'Tier-B policy missing');
  const {verdict} = require(file);
  const pr = {user:{login:'alex'},head:{sha:'abc'},labels:[{name:'tier-b'}]};
  assert.equal(verdict(pr, [{id:1,user:{login:'alex'},state:'APPROVED',commit_id:'abc'}]).conclusion,'failure');
  assert.equal(verdict(pr, [{id:1,user:{login:'fable'},state:'APPROVED',commit_id:'abc'}]).conclusion,'success');
});
test('stale, dismissed and superseded approvals cannot pass', () => {
  assert.ok(fs.existsSync(file), 'Tier-B policy missing');
  const {verdict} = require(file);
  const pr = {user:{login:'alex'},head:{sha:'abc'},labels:[{name:'tier-b'}]};
  for (const state of ['DISMISSED','CHANGES_REQUESTED']) {
    assert.equal(verdict(pr,[{id:1,user:{login:'fable'},state:'APPROVED',commit_id:'abc'},
      {id:2,user:{login:'fable'},state,commit_id:'abc'}]).conclusion,'failure');
  }
  assert.equal(verdict(pr,[{id:1,user:{login:'fable'},state:'APPROVED',commit_id:'old'}]).conclusion,'failure');
  assert.equal(verdict({...pr,labels:[]},[]).conclusion,'success');
});
