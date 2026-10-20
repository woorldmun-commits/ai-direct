import {createHmac} from 'node:crypto';
import {isIP} from 'node:net';

// Set the header name only behind an edge that unconditionally overwrites it (deploy/Caddyfile).
export function proxyClientHeaders(request:Request,path:string):Record<string,string>{
 const header=process.env.REKVERO_CLIENT_IP_HEADER,key=process.env.API_PROXY_HMAC_KEY;
 if(!header||!key||key.length<32)return {};
 const ip=request.headers.get(header);
 if(!ip||!isIP(ip))return {};
 const value=Math.floor(Date.now()/1000)+':'+ip;
 return {'X-Inrou-Client':value,'X-Inrou-Proxy-Signature':createHmac('sha256',key).update(`${request.method}\n${path}\n${value}`).digest('hex')};
}
