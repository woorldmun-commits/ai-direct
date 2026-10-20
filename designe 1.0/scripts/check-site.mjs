import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';

function load(path, env, dependencies={}) {
 const exports={};
 const code=ts.transpileModule(readFileSync(new URL(path,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 new Function('exports','process','require',code)(exports,{env},name=>{assert(name in dependencies);return dependencies[name];});
 return exports;
}
for(const [url,publicSite] of [[undefined,false],['http://127.0.0.1:3120',false],['https://localhost',false],['https://preview.localhost',false],['https://127.0.0.2',false],['https://intranet.local',false],['https://rekvero.example',true]]) {
 const site=load('../lib/site.ts',{NEXT_PUBLIC_SITE_URL:url});
 assert.equal(site.PUBLIC_SITE_CONFIGURED,publicSite,url);
 const sitemap=load('../app/sitemap.ts',{}, {'@/lib/site':site}).default();
 const robots=load('../app/robots.ts',{}, {'@/lib/site':site}).default();
 assert.deepEqual(sitemap.map(entry=>entry.url),publicSite?[site.SITE_URL,...["features","how-it-works","integrations","pricing","security","faq","contact"].map(path=>site.SITE_URL+"/"+path)]:[]);
 assert.deepEqual(robots.rules.disallow,publicSite?['/api/']:'/');
 assert.equal(robots.sitemap,publicSite?site.SITE_URL+'/sitemap.xml':undefined);
}
for(const url of ['http://rekvero.example','https://user:secret@rekvero.example','https://rekvero.example/path','https://rekvero.example?x=1'])assert.throws(()=>load('../lib/site.ts',{NEXT_PUBLIC_SITE_URL:url}));
const api = load('../lib/api-origin.ts',{REKVERO_API_URL:'https://new.example',ADPILOT_API_URL:'https://legacy.example',REKVERO_APP_ORIGIN:'https://rekvero.example',ADPILOT_APP_ORIGIN:'https://legacy.example'});
assert.equal(api.apiOrigin().origin,'https://new.example');
assert.equal(api.appOrigin(new Request('http://localhost:3000/api/auth/logout')),'https://rekvero.example');
assert.equal(load('../lib/api-origin.ts',{ADPILOT_API_URL:'https://legacy.example'}).apiOrigin().origin,'https://legacy.example');
assert.equal(load('../lib/api-origin.ts',{REKVERO_API_URL:'http://untrusted.example',ADPILOT_API_URL:'https://legacy.example'}).apiOrigin(),null);
console.log('PASS site origins, preview exclusion, public-only sitemap and robots');
