import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import * as crypto from 'node:crypto';
import * as net from 'node:net';

function load(file,deps={}){
 const exports={};const code=ts.transpileModule(readFileSync(new URL(file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 new Function('exports','require',code)(exports,name=>{assert(name in deps,name);return deps[name];});return exports;
}
const origin=load('../lib/api-origin.ts');
const client=load('../lib/proxy-client.ts',{'node:crypto':crypto,'node:net':net});
const auth=load('../lib/auth-proxy.ts',{'./api-origin':origin,'./proxy-client':client});
const {proxyDirect}=load('../lib/direct-proxy.ts',{'./api-origin':origin,'./auth-proxy':auth});
const previous={...process.env};const savedFetch=globalThis.fetch;
try{
 process.env.INROU_API_URL='http://127.0.0.1:8081';process.env.INROU_APP_ORIGIN='https://app.example';
 process.env.API_PROXY_HMAC_KEY='a'.repeat(32);process.env.INROU_CLIENT_IP_HEADER='x-real-ip';
 const req=new Request('https://app.example/api/auth/email/login',{method:'POST',headers:{'x-real-ip':'203.0.113.10'}});
 const signed=client.proxyClientHeaders(req,'/api/v1/auth/email/login');
 assert.match(signed['X-Inrou-Client'],/^\d+:203\.0\.113\.10$/);
 assert.equal(signed['X-Inrou-Proxy-Signature'],crypto.createHmac('sha256','a'.repeat(32)).update(`POST\n/api/v1/auth/email/login\n${signed['X-Inrou-Client']}`).digest('hex'));
 assert.deepEqual(client.proxyClientHeaders(new Request(req.url,{headers:{'x-real-ip':'x, 203.0.113.10'}}),'/api'),{});
 const cookie='session='+'s'.repeat(43)+'; inrou_direct_flow=synthetic-flow';let calls=0;
 globalThis.fetch=async(url,options)=>{
  calls++;assert.equal(new URL(url).origin,'http://127.0.0.1:8081');
  assert(!options.headers.get('cookie').includes('other='));
  return new Response(null,{status:303,headers:{location:'/workspace?view=integrations&workspace=ws_1&direct=connected','Set-Cookie':'inrou_direct_flow=; Max-Age=0; HttpOnly'}});
 };
 const callback=new Request('https://app.example/api/direct/callback?state=state&code=code',{headers:{cookie:cookie+'; other=private'}});
 const response=await proxyDirect(callback);
 assert.equal(response.status,303);assert.match(response.headers.get('set-cookie'),/Max-Age=0/);
 assert.equal(response.headers.get('cache-control'),'no-store');
 assert.equal((await proxyDirect(new Request(callback.url))).status,401);
 assert.equal((await proxyDirect(new Request(callback.url+'&code=duplicate',{headers:{cookie}}))).status,400);
 assert.equal((await proxyDirect(new Request('https://app.example/api/workspaces/ws_1/direct/start',{method:'POST',headers:{cookie,origin:'https://evil.example'}}),'ws_1')).status,403);
 assert.equal(calls,1);
 globalThis.fetch=async()=>new Response(null,{status:303,headers:{location:'https://evil.example'}});
 assert.equal((await proxyDirect(callback)).status,502);
 console.log('PASS: Direct proxy session/CSRF/redirect bounds and signed visitor IPs.');
}finally{globalThis.fetch=savedFetch;for(const key of Object.keys(process.env))if(!(key in previous))delete process.env[key];Object.assign(process.env,previous);}
