import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createStreamServer} from '../src/stream-server.mjs';
import {runSuite} from '../src/scenarios.mjs';
const out=path.resolve(process.env.STREAM_OUT||'results');fs.mkdirSync(out,{recursive:true});
const app=createStreamServer({out});let report,shutdown;
try {const address=await app.listen(0);report=await runSuite({base:`http://127.0.0.1:${address.port}`,kind:'node-real-wire',onCase:r=>{if(r.phase==='finish')console.log(`${r.passed?'PASS':'FAIL'} ${r.name}: ${r.conclusion||r.error}`);}});fs.writeFileSync(path.join(out,'wire-receipt.json'),JSON.stringify(report,null,2)+'\n');assert.equal(report.results.filter(r=>!r.passed).length,0,'One or more real-wire scenarios failed');}
finally{shutdown=await app.stop('wire-suite-complete');fs.writeFileSync(path.join(out,'wire-shutdown.json'),JSON.stringify(shutdown,null,2)+'\n');}
assert.equal(shutdown.remainingLabs,0);assert.equal(shutdown.remainingSockets,0);console.log(`WIRE_SUITE ${report.results.length}/${report.results.length}; all connections stopped`);
