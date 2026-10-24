import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {candidateUrl} from './candidate-path.mjs';
const {sha256,hash,frame}=await import(candidateUrl('src/protocol.mjs'));
const standard=s=>crypto.createHash('sha256').update(s).digest('hex');

test('portable SHA-256 equals Node crypto across padding boundaries and Unicode',()=>{
 const lengths=[0,1,2,7,54,55,56,57,62,63,64,65,119,120,121,127,128,129,255,256,257,1023,1024,65536];
 for(const n of lengths)for(const unit of ['a','\u0000','é','😀','\ud800']){const s=unit.repeat(n);assert.equal(sha256(s),standard(s),`length ${n} unit ${JSON.stringify(unit)}`);}
});

test('portable SHA-256 equals Node crypto on 1000 deterministic byte-valued strings',()=>{
 let seed=0x284961;const rand=()=>seed=(Math.imul(seed,1664525)+1013904223)>>>0;
 for(let i=0;i<1000;i++){const length=rand()%2048;let s='';for(let j=0;j<length;j++)s+=String.fromCharCode(rand()%65536);assert.equal(sha256(s),standard(s));}
});

test('canonical job hash matches independently constructed fixed fixture serialization',()=>{
 for(let seq=1;seq<=500;seq++){
  const p=(seq%101)/100;
  const serialized=JSON.stringify({instrument:{market:'synthetic-market',outcome:'yes',provider:'synthetic-provider',token:'synthetic-yes'},p,seq,source:{id:`fixture-${seq}`,kind:'synthetic'}});
  assert.equal(hash(frame(seq,p)),standard(serialized));
 }
});
