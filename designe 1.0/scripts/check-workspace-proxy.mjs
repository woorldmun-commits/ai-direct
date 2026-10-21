import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {readFileSync} from 'node:fs';
import net from 'node:net';
import ts from 'typescript';
function load(file,dependencies={}){
 const exports={};const code=ts.transpileModule(readFileSync(new URL(file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 new Function('exports','require',code)(exports,name=>{assert(name in dependencies,name);return dependencies[name];});return exports;
}
const origin=load('../lib/api-origin.ts'),client=load('../lib/proxy-client.ts',{'node:crypto':crypto,'node:net':net}),auth=load('../lib/auth-proxy.ts',{'./api-origin':origin,'./proxy-client':client}),paths=load('../lib/workspace-path.ts');
const {proxyWorkspace}=load('../lib/workspace-proxy.ts',{'./api-origin':origin,'./auth-proxy':auth,'./workspace-path':paths});
const token='a'.repeat(43),base='https://rekvero.example',path='/workspaces/ws_1/insights';
const request=(method='GET',overrides={})=>new Request(base+'/api'+path,{method,headers:{Cookie:'unrelated=private; session='+token,...(method==='POST'?{Origin:base,'Content-Type':'application/json'}:{})},...(method==='POST'?{body:'{}'}:{}),...overrides});
const oldApp=process.env.ADPILOT_APP_ORIGIN;delete process.env.ADPILOT_APP_ORIGIN;
const old=process.env.ADPILOT_API_URL,originalFetch=globalThis.fetch;process.env.ADPILOT_API_URL='http://127.0.0.1:8000';let calls=0;
try{
 globalThis.fetch=async(url,options)=>{calls++;assert.equal(new URL(url).origin,'http://127.0.0.1:8000');assert.equal(options.headers.get('Cookie'),'session='+token);assert.equal(options.redirect,'error');assert.equal(options.cache,'no-store');return Response.json({status:'ok'});};
 for(const bad of ['/workspaces/ws_0/insights','/workspaces/ws_1/../../me','/workspaces/ws_1/insights?url=https://evil.example','/workspaces/ws_1/recommendations/rec_1?x=1'])assert.equal((await proxyWorkspace(request(),bad)).status,404);
 assert.equal((await proxyWorkspace(request('POST'),path)).status,404);
 assert.equal(calls,0);
 const get=await proxyWorkspace(request(),path);assert.equal(get.status,200);assert.equal(get.headers.get('cache-control'),'no-store');assert.equal(get.headers.get('referrer-policy'),'no-referrer');
 assert.equal((await proxyWorkspace(request('GET',{headers:{Cookie:'session='+token+'; session='+token}}),path)).status,401);
 const post='/workspaces/ws_1/budget-plan';
 assert.equal((await proxyWorkspace(request('POST',{headers:{Origin:'https://evil.example'}}),post)).status,403);
 assert.equal((await proxyWorkspace(request('POST',{headers:{Origin:base,Cookie:'session='+token,'Content-Type':'text/plain'}}),post)).status,415);
 assert.equal((await proxyWorkspace(request('POST',{body:'x'.repeat(262145)}),post)).status,413);
 globalThis.fetch=async(_url,options)=>{assert.equal(options.headers.get('Origin'),base);assert.equal(options.body,'{}');return Response.json({error:{code:'stale_version'}},{status:409,headers:{'Set-Cookie':'unrelated=leak'}});};
 const conflict=await proxyWorkspace(request('POST'),post);assert.equal(conflict.status,409);assert.equal(conflict.headers.get('set-cookie'),null);
 globalThis.fetch=async()=>new Response('<html>not json</html>');assert.equal((await proxyWorkspace(request(),path)).status,502);
 globalThis.fetch=async()=>new Response('x'.repeat(1048577),{headers:{'Content-Type':'application/json'}});assert.equal((await proxyWorkspace(request(),path)).status,502);
 process.env.ADPILOT_APP_ORIGIN=base;
 globalThis.fetch=async(_url,options)=>{assert.equal(options.headers.get('Origin'),base);return Response.json({status:'ok'});};
 const internal=new Request('http://localhost:3000/api'+post,{method:'POST',headers:{Origin:base,Cookie:'session='+token,'Content-Type':'application/json'},body:'{}'});
 assert.equal((await proxyWorkspace(internal,post)).status,200);
 assert.equal((await proxyWorkspace(request('POST',{headers:{Origin:'https://evil.example',Cookie:'session='+token,'Content-Type':'application/json'}}),post)).status,403);
 process.env.ADPILOT_APP_ORIGIN='https://user:secret@example.com';assert.equal((await proxyWorkspace(request(),path)).status,503);
 delete process.env.ADPILOT_APP_ORIGIN;
 delete process.env.ADPILOT_API_URL;assert.equal((await proxyWorkspace(request(),path)).status,503);
 process.env.REKVERO_SESSION_COOKIE='rekvero_session';process.env.ADPILOT_SESSION_COOKIE='legacy_session';process.env.ADPILOT_API_URL='http://127.0.0.1:8000';
 globalThis.fetch=async(_url,options)=>{assert.equal(options.headers.get('Cookie'),'rekvero_session='+token);return Response.json({status:'ok'});};
 assert.equal((await proxyWorkspace(request('GET',{headers:{Cookie:'rekvero_session='+token}}),path)).status,200);
 assert.equal((await proxyWorkspace(request('GET',{headers:{Cookie:'legacy_session='+token}}),path)).status,401);
 delete process.env.REKVERO_SESSION_COOKIE;delete process.env.ADPILOT_SESSION_COOKIE;
 console.log('PASS private workspace bridge: closed paths, origin, session, bounded bodies, private headers and safe upstream responses');
}finally{if(oldApp===undefined)delete process.env.ADPILOT_APP_ORIGIN;else process.env.ADPILOT_APP_ORIGIN=oldApp;globalThis.fetch=originalFetch;if(old===undefined)delete process.env.ADPILOT_API_URL;else process.env.ADPILOT_API_URL=old;}
