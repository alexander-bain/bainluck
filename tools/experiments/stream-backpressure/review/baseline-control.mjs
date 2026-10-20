import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createStreamServer} from '../baseline/stream-server.mjs';
import {FakeResponse,createLab,open,action} from './mock-http.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const app=createStreamServer({out:path.join(here,'baseline-output')});
try {
 const lab=await createLab(app),slow=new FakeResponse({blocked:true}),fast=new FakeResponse();
 await open(app,lab,'slow-control',slow);await open(app,lab,'fast-control',fast);
 const afterHandshake=slow.writeCalls;
 for(let seq=1;seq<=128;seq++)await action(app,lab,{action:'publish',seq,p:seq/128});
 assert.equal(slow.destroyed,false);assert.ok(slow.totalBytes<2*1024*1024);
 const report={scope:'Independent pure fake-response HTTP handler test; no TCP listener, no external data',baselineInvariantFailure:slow.writeCalls>1,firstFalseFollowedByFurtherWrites:slow.writeCalls-1,slowWriteCalls:slow.writeCalls,handshakeWriteCalls:afterHandshake,slowNodeLikeBufferedBytes:slow.writableLength,fastFinal:fast.messages().at(-1)?.payload?.p,fastFrames:fast.messages().length,disconnectOccurred:slow.destroyed,limits:'2 clients, 128 publications, <2MiB application input; simulated writableLength is not actual Node or kernel memory'};
 assert.equal(report.baselineInvariantFailure,true);assert.equal(report.fastFinal,1);
 fs.writeFileSync(path.join(here,'baseline-control.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
} finally {await app.stop('independent-baseline-control');}
