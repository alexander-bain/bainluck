import {spawn} from 'node:child_process';
// Bound each owned Node process without requiring GNU timeout on the host.
const child=spawn(process.execPath,process.argv.slice(2),{stdio:'inherit'});
let hardKill;
const deadline=setTimeout(()=>{console.error('ERROR: 30-minute process limit reached; stopping child.');child.kill('SIGTERM');hardKill=setTimeout(()=>child.kill('SIGKILL'),2000);},30*60*1000);
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{child.kill(signal);hardKill=setTimeout(()=>child.kill('SIGKILL'),2000);});
child.once('error',error=>{clearTimeout(deadline);clearTimeout(hardKill);console.error(`ERROR: child launch failed: ${error.message}`);process.exit(1);});
child.once('exit',(code,signal)=>{clearTimeout(deadline);clearTimeout(hardKill);process.exit(code??(signal?1:0));});
