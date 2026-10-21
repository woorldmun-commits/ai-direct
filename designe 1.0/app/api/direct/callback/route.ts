import {proxyDirect} from '@/lib/direct-proxy';
export const dynamic='force-dynamic';
export function GET(request:Request){return proxyDirect(request);}
