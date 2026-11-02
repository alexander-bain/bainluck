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

test('an unlabeled PR cannot overwrite a failing check on a shared head', async () => {
  const {evaluate} = require(file);
  const prs = [
    {number:1,state:'open',user:{login:'alex'},head:{sha:'same'},labels:[{name:'tier-b'}]},
    {number:2,state:'open',user:{login:'alex'},head:{sha:'same'},labels:[]},
  ];
  const created=[];
  const github={rest:{pulls:{get:()=>{},list:()=>{},listReviews:()=>{}},checks:{listForRef:()=>{},create:async x=>created.push(x)}},
    paginate:async (fn,args)=>fn===github.rest.pulls.list ? prs : []};
  github.rest.pulls.get=async(args)=>({data:prs.find(pr=>pr.number===args.pull_number)});
  await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},payload:{pull_request:{number:2}}});
  assert.equal(created.length,1);
  assert.equal(created[0].conclusion,'failure');
});
