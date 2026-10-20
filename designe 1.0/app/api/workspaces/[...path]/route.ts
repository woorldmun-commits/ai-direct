import {proxyWorkspace} from '@/lib/workspace-proxy';

async function handle(request:Request,context:{params:Promise<{path:string[]}>}){
 const {path}=await context.params;
 return proxyWorkspace(request,'/workspaces/'+path.join('/')+new URL(request.url).search);
}
export const GET=handle;
export const POST=handle;
