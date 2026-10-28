import {proxyDirect} from '@/lib/direct-proxy';
type Context={params:Promise<{workspace:string;action?:string[]}>};
export const dynamic='force-dynamic';
async function handle(request:Request,context:Context){
 const {workspace,action=[]}=await context.params;
 if(action.length>1||action.length===1&&!['start','sync','complete'].includes(action[0]))return new Response(null,{status:404});
 return proxyDirect(request,workspace);
}
export const GET=handle;
export const POST=handle;
