import {apiOrigin,appOrigin} from './api-origin';
import {readLimited} from './auth-proxy';
import {workspacePath} from './workspace-path';

const privateHeaders={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'};
const error=(status:number)=>Response.json({error:{message:'Запрос не выполнен. Проверьте доступ и данные или повторите позже.'}},{status,headers:privateHeaders});

export async function proxyWorkspace(request:Request,path:string):Promise<Response>{
 if(!workspacePath(path,request.method))return error(404);
 const publicOrigin=appOrigin(request);
 if(!publicOrigin)return error(503);
 if(request.method==='POST'&&request.headers.get('origin')!==publicOrigin)return error(403);
 const base=apiOrigin(),name=process.env.INROU_SESSION_COOKIE??'session';
 if(!base||! /^[A-Za-z0-9_-]{1,64}$/.test(name))return error(503);
 const selected=(request.headers.get('cookie')||'').split(';').map(value=>value.trim()).filter(value=>value.startsWith(name+'='));
 if(selected.length!==1||!new RegExp('^'+name+'=[A-Za-z0-9_-]{32,128}$').test(selected[0]))return error(401);
 const headers=new Headers({Accept:'application/json',Cookie:selected[0]});
 let body:string|undefined;
 if(request.method==='POST'){
  if(request.headers.get('content-type')?.split(';')[0].trim()!=='application/json')return error(415);
  try{body=await readLimited(request.body,262144);}catch{return error(413);}
  if(!body)return error(400);
  headers.set('Content-Type','application/json');headers.set('Origin',publicOrigin);
 }
 try{
  const response=await fetch(new URL('/api/v1'+path,base),{method:request.method,headers,body,cache:'no-store',redirect:'error',signal:AbortSignal.timeout(8000)});
  if(!response.headers.get('content-type')?.includes('application/json'))return error(502);
  const raw=await readLimited(response.body,1048576);
  const value:unknown=JSON.parse(raw);
  if(!value||typeof value!=='object')return error(502);
  // Only a bounded JSON body/status is forwarded; upstream cookies and redirects never cross this boundary.
  return Response.json(value,{status:response.status,headers:privateHeaders});
 }catch{return error(502);}
}
