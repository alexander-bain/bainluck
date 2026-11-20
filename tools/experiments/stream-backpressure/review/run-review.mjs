import {spawn} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const cwd=path.dirname(fileURLToPath(import.meta.url));let child,hardKill,timedOut=false;
const timeout=setTimeout(()=>{timedOut=true;console.error('Independent review exceeded its 30-second deadline. Stopping only the owned test process.');child?.kill('SIGTERM');hardKill=setTimeout(()=>child?.kill('SIGKILL'),1000);},30000);
for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>{child?.kill(signal);clearTimeout(timeout);hardKill=setTimeout(()=>child?.kill('SIGKILL'),1000);});
try{for(const file of ['baseline-control.mjs','candidate-review.mjs','audit-wire-receipt.mjs']){console.log(`\nRUN ${file}`);const result=await new Promise((resolve,reject)=>{child=spawn(process.execPath,[file],{cwd,stdio:'inherit'});child.once('error',reject);child.once('exit',(code,signal)=>resolve({code,signal}));});if(result.code!==0||timedOut){process.exitCode=result.code||1;break;}}}finally{clearTimeout(timeout);clearTimeout(hardKill);}
