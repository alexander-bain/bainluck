const fs=require('fs'),path=require('path');
const base=process.argv[2],out=process.argv[3],own=__dirname;
const deps='/Users/bain/bainluck/frontend/node_modules';
const ts=require(deps+'/typescript'),webpack=require(deps+'/webpack');
fs.writeFileSync(out+'/loader.cjs',`const ts=require(${JSON.stringify(deps+'/typescript')});module.exports=function(s){return ts.transpileModule(s,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.ESNext}}).outputText;}`);
fs.writeFileSync(out+'/entry.tsx',`import React from 'react';import{createRoot}from'react-dom/client';import{SWRConfig}from'swr';import EventPage from ${JSON.stringify(base+'/app/events/[id]/page.tsx')};import{AnalyticsProvider}from ${JSON.stringify(base+'/components/Analytics/AnalyticsProvider.tsx')};import{AuthProvider}from ${JSON.stringify(base+'/components/AuthProvider.tsx')};createRoot(document.getElementById('root')!).render(<SWRConfig value={{provider:()=>new Map(),revalidateOnFocus:false,revalidateOnReconnect:false}}><AnalyticsProvider><AuthProvider><EventPage params={{id:document.body.dataset.event!}}/></AuthProvider></AnalyticsProvider></SWRConfig>);`);
const aliases={'next/navigation':own+'/navigation.ts','next/link':own+'/link.tsx','next/image':own+'/image.tsx','next/dynamic':own+'/dynamic.tsx','@/hooks/useAuth':own+'/auth.ts','@':base};
webpack({mode:'development',devtool:false,entry:out+'/entry.tsx',output:{path:out,filename:'bundle.js',publicPath:'/'},plugins:[new webpack.IgnorePlugin({resourceRegExp:/^firebase\/(app|auth)$/}),new webpack.DefinePlugin({'process.env.NEXT_PUBLIC_API_URL':'location.origin','process.env.NODE_ENV':JSON.stringify('development')})],resolve:{extensions:['.tsx','.ts','.js'],modules:[deps],alias:aliases},module:{rules:[{test:/\.tsx?$/,exclude:/node_modules/,use:out+'/loader.cjs'}]}},async(err,stats)=>{
 if(err||stats.hasErrors()){console.error(err||stats.toString({all:false,errors:true}));process.exitCode=1;return;}
 console.log(stats.toString({all:false,assets:true,warnings:true}));
 const postcss=require(deps+'/postcss'),tailwind=require(deps+'/tailwindcss');
 const configPath=['tailwind.config.ts','tailwind.config.js'].map(x=>base+'/'+x).find(x=>fs.existsSync(x));
 const compiled=ts.transpileModule(fs.readFileSync(configPath,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText;
 const mod={exports:{}};new Function('module','exports','require',compiled)(mod,mod.exports,(name)=>require(deps+'/'+name));
 const conf=mod.exports.default||mod.exports;conf.content=[base+'/**/*.{ts,tsx}'];
 const css=await postcss([tailwind(conf)]).process(fs.readFileSync(base+'/app/globals.css','utf8').replace('@import "./design-tokens.css";',fs.readFileSync(base+'/app/design-tokens.css','utf8')),{from:base+'/app/globals.css'});fs.writeFileSync(out+'/style.css',css.css);
});
