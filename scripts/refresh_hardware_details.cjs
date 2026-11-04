/* Reuse browser calculations to maintain an optional public fallback snapshot. */
const fs=require('node:fs'),vm=require('node:vm'),{execFile}=require('node:child_process'),path=require('node:path');
const root=path.resolve(__dirname,'..');
function get(url){return new Promise((resolve,reject)=>execFile('curl',['--fail','--silent','--show-error','--max-time','25',String(url)],{maxBuffer:20*1024*1024,encoding:'utf8'},(error,body)=>error?reject(error):resolve(body)))}
const context={URL,Date,Map,Set,AbortSignal,console,setTimeout:(f,t)=>{const timer=setTimeout(f,t);timer.unref();return timer},clearTimeout,window:{},document:{createElement:()=>({remove(){}}),head:{append(script){get(script.src).then(body=>vm.runInContext(body,context)).catch(()=>script.onerror())}}},fetch:async url=>({ok:true,json:async()=>JSON.parse(await get(url))})};
context.window=context;vm.createContext(context);
for(const file of ['hardware-metrics.js','live-data.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
(async()=>{const file=path.join(root,'data/hardware.json'),snapshot=JSON.parse(fs.readFileSync(file,'utf8'));await context.RadarLive.enrichHardwareLeaders(snapshot.stocks,console.log);const selected=snapshot.stocks.filter(s=>s.leaderRank);if(selected.some(s=>!s.history?.high||!s.fundamentals?.reportDate))throw Error('Incomplete leader history or financial snapshot');fs.writeFileSync(file,JSON.stringify(snapshot));console.log('Updated fallback details for '+selected.length+' leaders');})().catch(error=>{console.error(error);process.exitCode=1});
