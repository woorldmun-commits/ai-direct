import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
function load(file){
  const exports={};
  new Function('exports','require',ts.transpileModule(readFileSync(new URL(file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exports,name=>{assert.equal(name,'@/lib/site');return {SITE_URL:'https://example.test',PUBLIC_SITE_CONFIGURED:true};});
  return exports.default;
}
const previous=process.env.INROU_STAGING;
try{
  for(const staging of [false,true]){
    if(staging)process.env.INROU_STAGING='1';else delete process.env.INROU_STAGING;
    const robots=load('../app/robots.ts')();
    const headers=(await load('../next.config.ts').headers())[0].headers;
    assert.equal(headers.some(h=>h.key==='X-Robots-Tag'&&h.value==='noindex, nofollow'),staging);
    assert.equal(robots.rules.disallow,staging?'/':robots.rules.disallow);
    assert.equal(robots.rules.allow,staging?undefined:'/');
    assert.equal('sitemap' in robots,!staging);
  }
}finally{if(previous===undefined)delete process.env.INROU_STAGING;else process.env.INROU_STAGING=previous;}
console.log('PASS staging: noindex+robots closed only on staging; normal public configuration preserved');
