import {apiOrigin} from '@/lib/api-origin';
export const dynamic='force-dynamic';
export async function GET(){
 const origin=apiOrigin();
 try{
  if(!origin)throw new Error();
  const r=await fetch(new URL('/api/v1/health',origin),{cache:'no-store',signal:AbortSignal.timeout(3000)});
  return Response.json({status:r.ok?'ok':'unavailable'},{status:r.ok?200:503,headers:{'Cache-Control':'no-store'}});
 }catch{return Response.json({status:'unavailable'},{status:503,headers:{'Cache-Control':'no-store'}});}
}
