import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';

function load(path, env, dependencies={}) {
 const exports={};
 const code=ts.transpileModule(readFileSync(new URL(path,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 new Function('exports','process','require',code)(exports,{env},name=>{assert(name in dependencies);return dependencies[name];});
 return exports;
}
for(const [url,publicSite] of [[undefined,false],['http://127.0.0.1:3120',false],['https://localhost',false],['https://preview.localhost',false],['https://127.0.0.2',false],['https://intranet.local',false],['https://inrou.example',true]]) {
 const site=load('../lib/site.ts',{NEXT_PUBLIC_SITE_URL:url});
 assert.equal(site.PUBLIC_SITE_CONFIGURED,publicSite,url);
 const sitemap=load('../app/sitemap.ts',{}, {'@/lib/site':site}).default();
 const robots=load('../app/robots.ts',{}, {'@/lib/site':site}).default();
 assert.deepEqual(sitemap.map(entry=>entry.url),publicSite?[site.SITE_URL,...["features","how-it-works","agencies","business","integrations","pricing","security","faq","contact","about"].map(path=>site.SITE_URL+"/"+path)]:[]);
 assert.deepEqual(robots.rules.disallow,publicSite?['/api/']:'/');
 assert.equal(robots.sitemap,publicSite?site.SITE_URL+'/sitemap.xml':undefined);
}
for(const url of ['http://inrou.example','https://user:secret@inrou.example','https://inrou.example/path','https://inrou.example?x=1'])assert.throws(()=>load('../lib/site.ts',{NEXT_PUBLIC_SITE_URL:url}));
const api = load('../lib/api-origin.ts',{INROU_API_URL:'https://new.example',INROU_APP_ORIGIN:'https://inrou.example'});
assert.equal(api.apiOrigin().origin,'https://new.example');
assert.equal(api.appOrigin(new Request('http://localhost:3000/api/auth/logout')),'https://inrou.example');
assert.equal(load('../lib/api-origin.ts',{INROU_API_URL:'https://legacy.example'}).apiOrigin().origin,'https://legacy.example');
assert.equal(load('../lib/api-origin.ts',{INROU_API_URL:'http://untrusted.example'}).apiOrigin(),null);
console.log('PASS site origins, preview exclusion, public-only sitemap and robots');
