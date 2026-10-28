import {apiOrigin} from './api-origin';
import {readLimited} from './auth-proxy';

export async function relayBillingWebhook(request:Request):Promise<Response> {
 const headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
 const fail=(status:number)=>Response.json({accepted:false},{status,headers});
 if(request.method!=='POST')return fail(405);
 if(request.headers.get('content-type')?.split(';')[0].trim()!=='application/json')return fail(415);
 const base=apiOrigin();if(!base)return fail(503);
 let body:string;
 try{body=await readLimited(request.body,65536);JSON.parse(body);}catch{return fail(400);}
 try{
  // Authentication is a provider GET in the backend; caller headers are never proof of payment.
  const response=await fetch(new URL('/api/v1/billing/yookassa/webhook',base),{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body,cache:'no-store',redirect:'error',signal:AbortSignal.timeout(20000)});
  return response.ok?Response.json({accepted:true},{headers}):fail(response.status);
 }catch{return fail(503);}
}
