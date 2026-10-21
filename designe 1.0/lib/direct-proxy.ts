import {apiOrigin, appOrigin} from './api-origin';
import {readLimited} from './auth-proxy';

const privateHeaders = {'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'};
const fail = (status:number) => Response.json({error:{message:'Не удалось подключить Директ. Проверьте доступ и повторите.'}}, {status, headers:privateHeaders});

export async function proxyDirect(request:Request, workspace?:string):Promise<Response>{
 const callback = workspace === undefined;
 const incoming = new URL(request.url);
 const path = callback ? '/direct/callback' : `/workspaces/${workspace}/direct${incoming.pathname.endsWith('/start')?'/start':incoming.pathname.endsWith('/sync')?'/sync':''}`;
 if(!callback&&!/^ws_[1-9]\d{0,18}$/.test(workspace!))return fail(404);
 if(request.method!==(callback||path.endsWith('/direct')?'GET':'POST'))return fail(405);
 const base=apiOrigin(), origin=appOrigin(request);
 if(!base||!origin)return fail(503);
 if(request.method==='POST'&&request.headers.get('origin')!==origin)return fail(403);
 const name=process.env.REKVERO_SESSION_COOKIE||process.env.ADPILOT_SESSION_COOKIE||'session';
 if(!/^[A-Za-z0-9_-]{1,64}$/.test(name))return fail(503);
 const cookies=(request.headers.get('cookie')||'').split(';').map(c=>c.trim()).filter(c=>
   (c.startsWith(name+'=')||callback&&c.startsWith('inrou_direct_flow='))&&/^[A-Za-z0-9_-]+=[A-Za-z0-9_.=-]{1,8192}$/.test(c));
 if(cookies.filter(c=>c.startsWith(name+'=')).length!==1)return fail(401);
 const target=new URL('/api/v1'+path,base);
 if(callback)for(const key of ['state','code','error']){
  const values=incoming.searchParams.getAll(key);
  if(values.length>1||(values[0]?.length||0)>2048)return fail(400);
  if(values[0])target.searchParams.set(key,values[0]);
 }
 const headers=new Headers({Accept:'application/json',Cookie:cookies.join('; ')});
 let body:string|undefined;
 if(request.method==='POST'){
  if(request.headers.get('content-type')?.split(';')[0]!=='application/json')return fail(415);
  try{body=await readLimited(request.body,4096);}catch{return fail(413);}
  headers.set('Content-Type','application/json');headers.set('Origin',origin);
 }
 try{
  const response=await fetch(target,{method:request.method,headers,body,cache:'no-store',redirect:'manual',signal:AbortSignal.timeout(callback?120000:15000)});
  const outgoing=new Headers(privateHeaders);
  for(const cookie of response.headers.getSetCookie())outgoing.append('Set-Cookie',cookie);
  if(callback&&response.status===303){
   const location=response.headers.get('location');
   if(!location||!/^\/workspace\?view=integrations(?:&workspace=ws_[1-9]\d{0,18})?&direct=(connected|failed)$/.test(location))return fail(502);
   outgoing.set('Location',location);return new Response(null,{status:303,headers:outgoing});
  }
  if(!response.headers.get('content-type')?.includes('application/json'))return fail(502);
  const text=await readLimited(response.body,8192);
  outgoing.set('Content-Type','application/json');
  return new Response(text,{status:response.status,headers:outgoing});
 }catch{return fail(503);}
}
