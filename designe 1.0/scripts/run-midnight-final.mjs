import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const children=[];
const start=(command,args,env)=>{const child=spawn(command,args,{cwd:root,env:{...process.env,...env},windowsHide:true,stdio:'inherit'});children.push(child);return child;};
async function ready(url,child){
  for(let i=0;i<150;i++){
    assert.equal(child.exitCode,null,'Local QA process stopped before readiness');
    try{if((await fetch(url,{signal:AbortSignal.timeout(1000)})).ok)return;}catch{}
    await new Promise(resolve=>setTimeout(resolve,200));
  }
  throw new Error('Local QA process did not become ready');
}
for(const url of ['http://127.0.0.1:3121/api/v1/health','http://127.0.0.1:3130/api/health']){
  let occupied=false;try{await fetch(url,{signal:AbortSignal.timeout(500)});occupied=true;}catch{}
  assert(!occupied,'QA ports must be free; do not attach to an unrelated server');
}
try{
  const backend=start(path.join(root,'../backend/.venv/Scripts/python.exe'),['scripts/pilot-fixture.py'],{INROU_INTELLIGENCE_ENABLED:'1'});
  await ready('http://127.0.0.1:3121/api/v1/health',backend);
  const frontend=start(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3130'],{INROU_API_URL:'http://127.0.0.1:3121',INROU_APP_ORIGIN:'http://127.0.0.1:3130',INROU_DEMO:'1'});
  await ready('http://127.0.0.1:3130/api/health',frontend);
  const test=start(process.execPath,['scripts/check-midnight-final.mjs'],{});
  const code=await new Promise((resolve,reject)=>{test.on('error',reject);test.on('exit',resolve);});
  assert.equal(code,0,'Browser acceptance failed; see browser-results.json');
}finally{for(const child of children.reverse())if(child.exitCode===null)child.kill();}
