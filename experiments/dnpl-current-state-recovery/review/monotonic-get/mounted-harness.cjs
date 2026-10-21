/* Independent no-browser mounted hook checks. Run only when browser capture is idle. */
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const ROOT = path.resolve(__dirname, '../..');
const deps = path.join(ROOT, 'source/frontend/node_modules');
const React = require(path.join(deps, 'react'));
const {createRoot} = require(path.join(deps, 'react-dom/client'));
const {act} = React;
const {JSDOM} = require(path.join(deps, 'jsdom'));
const FakeTimers = require(path.join(deps, '@sinonjs/fake-timers'));
const esbuild = require(path.join(ROOT, 'harness/node_modules/esbuild'));

const hookPath = process.env.REVIEW_HOOK_SOURCE
  ? path.resolve(process.env.REVIEW_HOOK_SOURCE)
  : path.join(ROOT, 'monotonic-candidate/useLiveEventStream.ts');
// Stub only the controller boundary; React itself stays external and shared.

async function loadHook() {
  const built = await esbuild.build({
    entryPoints: [hookPath], bundle: true, write: false, platform: 'node', format: 'cjs',
    alias: {'@': path.join(ROOT, 'source/frontend')}, external: ['react'], nodePaths: [deps],
    plugins: [{name:'controlled-hook-boundaries', setup(build) {
      build.onResolve({filter:/liveStreamController$/}, () => ({path:'controller',namespace:'review'}));
      build.onResolve({filter:/(^|\/)blendPreview$/}, () => ({path:path.join(path.dirname(hookPath),'blendPreview.ts')}));
      build.onLoad({filter:/.*/,namespace:'review'}, () => ({loader:'js',contents:`
        export const TICK_INTERVAL_MS=5000;
        export const timerSchedule={};
        export function createLiveStreamController(deps){
          globalThis.__reviewControllers.push(deps);
          return {start(){deps.open();deps.onStatusChange('open')},stop(){},tick(){}};
        }
      `}));
    }}],
  });
  const loaded = new Module(hookPath, module);
  loaded.filename = hookPath;
  loaded.paths = [deps, ...module.paths];
  loaded._compile(built.outputFiles[0].text, hookPath);
  return loaded.exports.useLiveEventStream;
}

function deferred() {let resolve; const promise = new Promise(r=>resolve=r); return {promise,resolve};}

async function harness(options={}) {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', {url:'http://localhost'});
  const previous = {};
  for(const key of ['window','document','navigator','IS_REACT_ACT_ENVIRONMENT','fetch','EventSource','__reviewControllers']) previous[key]=global[key];
  global.window=dom.window;global.document=dom.window.document;global.navigator=dom.window.navigator;
  global.IS_REACT_ACT_ENVIRONMENT=true;global.__reviewControllers=[];
  const transports=[];
  dom.window.EventSource=global.EventSource=class {
    constructor(){this.listeners=new Map();transports.push(this);}
    addEventListener(type,fn){const list=this.listeners.get(type)??[];list.push(fn);this.listeners.set(type,list);}
    emit(type,data){for(const fn of this.listeners.get(type)??[])fn({type,data:JSON.stringify(data)});}
    close(){}
  };dom.window.evidence={};
  let visibility='visible';Object.defineProperty(dom.window.document,'visibilityState',{get:()=>visibility});
  const clock=FakeTimers.install({now:options.wallMs??100000,toFake:['Date','setTimeout','clearTimeout','setInterval','clearInterval','performance']});
  // Model the browser's Window timer receiver requirement. Node's fake timer
  // otherwise silently accepts `options.cancelTimer(id)` with this=options.
  const cancelTimer=global.clearTimeout;
  global.clearTimeout=function(id){
    if(this!==global&&this!==undefined)throw new TypeError('Illegal invocation: clearTimeout receiver');
    return cancelTimer(id);
  };
  const requests=[];
  global.fetch=(url,opts)=>{const response=deferred();requests.push({url,opts,response});return response.promise;};
  const useHook=await loadHook();let latest;let eid=1;let adopted;
  function Component(){latest=useHook(eid,true,undefined,undefined,adopted);return null;}
  const tree=()=>options.strict?React.createElement(React.StrictMode,null,React.createElement(Component)):React.createElement(Component);
  const root=createRoot(dom.window.document.getElementById('root'));
  await act(async()=>root.render(tree()));
  const wrap=async(fn)=>{await act(async()=>{fn();await Promise.resolve();await Promise.resolve();});};
  return {
    clock,requests,get transport(){return transports.at(-1)},get logs(){return dom.window.evidence.currentPreviewProbe??[]},get value(){return latest;},get controller(){return global.__reviewControllers.at(-1);},
    visible:()=>!!latest.blendPreview&&latest.blendPreviewNow<latest.blendPreview.expiresAt,
    act:wrap,tick:ms=>wrap(()=>clock.tick(ms)),
    hide:()=>wrap(()=>{visibility='hidden';dom.window.document.dispatchEvent(new dom.window.Event('visibilitychange'));}),
    navigate:async(id)=>{eid=id;await wrap(()=>root.render(tree()));},
    adopt:async(revision,id=eid)=>{adopted={eventId:id,revision};await wrap(()=>root.render(tree()));},
    close:async()=>{await wrap(()=>root.unmount());clock.uninstall();dom.window.close();for(const [k,v] of Object.entries(previous)){if(v===undefined)delete global[k];else global[k]=v;}},
  };
}


module.exports={harness,deferred};
