import 'server-only';
import {apiOrigin} from './api-origin';
import {readLimited} from './auth-proxy';
export async function emailEnabled():Promise<boolean>{
 const base=apiOrigin();if(!base)return false;
 try{
  const response=await fetch(new URL('/api/v1/auth/config',base),{cache:'no-store',redirect:'error',signal:AbortSignal.timeout(5000)});
  if(!response.ok||!response.headers.get('content-type')?.includes('application/json'))return false;
  const data:unknown=JSON.parse(await readLimited(response.body,1024));
  return !!data&&typeof data==='object'&&'email_enabled' in data&&data.email_enabled===true;
 }catch{return false;}
}
