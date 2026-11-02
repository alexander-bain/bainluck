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

test('refreshed Tier-B sibling joining a head cannot disappear from the group',async()=>{
  const {evaluate}=require(file);
  const old=[{number:1,state:'open',user:{login:'alex'},head:{sha:'old'},labels:[{name:'tier-b'}]},
    {number:2,state:'open',user:{login:'alex'},head:{sha:'same'},labels:[]}];
  const current=old.map(pr=>({...pr,head:{sha:'same'}}));const created=[];
  const github={rest:{pulls:{get:async args=>({data:current.find(p=>p.number===args.pull_number)}),list:()=>{},listReviews:()=>{}},checks:{listForRef:()=>{},create:async c=>created.push(c)}},
    paginate:async fn=>fn===github.rest.pulls.list?old:[]};
  await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},payload:{pull_request:{number:2}}});
  assert.equal(created.find(c=>c.head_sha==='same')?.conclusion,'failure');
});

test('a surviving event reconciles a dismissed review on another head',async()=>{
  const {evaluate}=require(file);
  const prs=[{number:1,state:'open',user:{login:'alex'},head:{sha:'a'},labels:[{name:'tier-b'}]},
    {number:2,state:'open',user:{login:'alex'},head:{sha:'b'},labels:[]}];const created=[];
  const github={rest:{pulls:{get:async args=>({data:prs.find(p=>p.number===args.pull_number)}),list:()=>{},listReviews:()=>{}},checks:{listForRef:()=>{},create:async c=>created.push(c)}},
    paginate:async fn=>fn===github.rest.pulls.list?prs:[]};
  await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},payload:{client_payload:{pull_number:2}}});
  assert.equal(created.find(c=>c.head_sha==='a')?.conclusion,'failure');
});

test('membership changes during the final check lookup force a fresh verdict',async()=>{
  const {evaluate}=require(file);
  let pr={number:1,state:'open',user:{login:'alex'},head:{sha:'same'},labels:[]};let changed=false;const created=[];
  const github={rest:{pulls:{get:async()=>({data:{...pr,labels:[...pr.labels]}}),list:()=>{},listReviews:()=>{}},checks:{listForRef:()=>{},create:async c=>created.push(c)}},
    paginate:async fn=>{
      if(fn===github.rest.pulls.list)return[{...pr,labels:[...pr.labels]}];
      if(fn===github.rest.checks.listForRef && !changed){changed=true;pr={...pr,labels:[{name:'tier-b'}]};}
      return[];
    }};
  await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},payload:{pull_request:{number:1}}});
  assert.equal(created.at(-1)?.conclusion,'failure');
});
