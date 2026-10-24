import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {candidateUrl} from './candidate-path.mjs';
const {Broker,Client,frame}=await import(candidateUrl('src/broker.mjs'));
const {Journal}=await import(candidateUrl('src/journal.mjs'));

test('persistent terminal reconnect conveys terminal state without reviving an owner or value',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'authority-review-'));const file=path.join(dir,'journal.wal');
 let journal=new Journal(file);try{
  const b=new Broker({journal}),token=b.claim('one');b.offer(token,frame(1,.6));assert.equal(b.terminal(token).terminal,true);journal.close();
  journal=new Journal(file);const r=new Broker({journal}),c=new Client({now:()=>0});r.open(c.start());const message=r.take(c.session);const result=c.accept(message);
  assert.equal(result.snapshot,true,JSON.stringify({result,message}));assert.equal(c.status,'terminal');assert.equal(c.current,null);assert.equal(r.claim('two').error,'terminal');
 }finally{journal.close();fs.rmSync(dir,{recursive:true});}
});
