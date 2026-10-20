import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import * as crypto from 'node:crypto';

function load(file, dependencies = {}) {
  const exports = {};
  const compiled = ts.transpileModule(readFileSync(new URL(file, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  new Function('exports', 'require', compiled)(exports, name => {
    assert(name in dependencies, `Unexpected dependency: ${name}`);
    return dependencies[name];
  });
  return exports;
}
const origin = load('../lib/api-origin.ts');
const { proxyAuth: requestAuth } = load('../lib/auth-proxy.ts', { './api-origin': origin });
const proxyAuth = async (...args) => {
  const response = await requestAuth(...args);
  assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
  return response;
};
const { validLegalDocument, legalDocument } = load('../lib/legal-document.ts', { 'server-only': {}, 'node:crypto': crypto, './api-origin': origin });
const text = 'Точный текст\r\nБез изменения пробелов.\n';
const document = { document: 'offer', version: '2026-10-01', locale: 'ru-RU', approved: true, text, sha256: crypto.createHash('sha256').update(text).digest('hex') };
assert(validLegalDocument(document, 'offer'));
assert(!validLegalDocument({ ...document, text: text.replaceAll('\r\n', '\n') }, 'offer'));
assert(!validLegalDocument({ ...document, sha256: 'a'.repeat(64) }, 'offer'));
assert(!validLegalDocument(document, 'pd_consent'));
assert(!validLegalDocument({ ...document, approved: 'true' }, 'offer'));
assert(!validLegalDocument({ ...document, version: '2026-10-02' }, 'offer'));
assert(!validLegalDocument({ ...document, locale: 'en-US' }, 'offer'));
assert(validLegalDocument({ ...document, approved: false }, 'offer'), 'Draft status must remain explicit, never coerced into approval.');
assert.equal(origin.apiOrigin('http://example.com'), null);
assert.equal(origin.apiOrigin('https://user:secret@example.com'), null);
assert.equal(origin.apiOrigin('https://example.com/credentials'), null);
assert.equal(origin.apiOrigin('http://127.0.0.1:8080').origin, 'http://127.0.0.1:8080');
const originalFetch = globalThis.fetch;
const previous = process.env.ADPILOT_API_URL;
process.env.ADPILOT_API_URL = 'http://127.0.0.1:8080';
let calls = 0;
const request = (path, options = {}) => new Request('https://rekvero.example/api/auth/' + path, options);
try {
  globalThis.fetch = async (url, options) => {
    calls++;
    assert.equal(new URL(url).pathname, '/api/v1/legal/documents/offer');
    assert.equal(new URL(url).searchParams.get('version'), '2026-10-01');
    assert.equal(new URL(url).searchParams.get('locale'), 'ru-RU');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.redirect, 'error');
    assert(options.signal instanceof AbortSignal);
    return Response.json(document);
  };
  assert.deepEqual(await legalDocument('offer'), document);
  assert.equal(await legalDocument('unrecognized'), null);
  assert.equal(calls, 1, 'Unknown legal key must not issue a request.');
  globalThis.fetch = async () => Response.json({ ...document, text: 'tampered' });
  assert.equal(await legalDocument('offer'), null);
  globalThis.fetch = async () => new Response(JSON.stringify(document), { headers: { 'Content-Type': 'text/plain' } });
  assert.equal(await legalDocument('offer'), null);
  globalThis.fetch = async () => new Response('x'.repeat(262145), { headers: { 'Content-Type': 'application/json' } });
  assert.equal(await legalDocument('offer'), null);
  globalThis.fetch = async () => { throw new Error('provider unavailable'); };
  assert.equal(await legalDocument('offer'), null);
  calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++;
    assert.equal(new URL(url).origin, 'http://127.0.0.1:8080');
    assert.equal(options.redirect, 'manual');
    assert.equal(options.cache, 'no-store');
    assert(!options.headers.get('Cookie')?.includes('unrelated'));
    return new Response(null, { status: 303, headers: { Location: '/workspace', 'Set-Cookie': 'session=valid; HttpOnly; Secure; Path=/' } });
  };
  assert.equal((await proxyAuth(request('logout', { method: 'POST', headers: { Origin: 'https://evil.example' } }), 'logout')).status, 403);
  assert.equal((await proxyAuth(request('secret'), 'secret')).status, 404);
  assert.equal((await proxyAuth(request('logout'), 'logout')).status, 404);
  assert.equal(calls, 0);
  const result = await proxyAuth(request('yandex/callback?code=valid&state=valid', { headers: { Cookie: 'unrelated=private; adpilot_oauth_flow=base64value==' } }), 'yandex/callback');
  assert.equal(result.status, 303);
  assert.equal(result.headers.get('location'), '/workspace');
  assert.match(result.headers.get('set-cookie'), /HttpOnly/);
  assert.equal(result.headers.get('cache-control'), 'no-store');
  assert.equal((await proxyAuth(request('yandex/callback?state=a&state=b'), 'yandex/callback')).status, 400);
  for (const operation of ['register','login','verify','reset-request','reset']) {
    const path='email/'+operation;
    assert.equal((await proxyAuth(request(path),path)).status,404);
    assert.equal((await proxyAuth(request(path,{method:'POST',headers:{Origin:'https://evil.example'}}),path)).status,403);
    globalThis.fetch=async (url,options)=>{
      assert.equal(new URL(url).pathname,'/api/v1/auth/'+path);
      assert.equal(options.body,'{}');
      assert.equal(options.headers.get('Origin'),'https://rekvero.example');
      return Response.json({status:'ok'});
    };
    assert.equal((await proxyAuth(request(path,{method:'POST',headers:{Origin:'https://rekvero.example','Content-Type':'application/json'},body:'{}'}),path)).status,200);
  }
  const {isPrivatePage}=load('../lib/private-page.ts');
  for(const path of ['/workspace','/workspace/recommendations/1','/signup','/login','/verify-email','/reset-password','/forgot-password']) assert(isPrivatePage(path),path);
  assert(!isPrivatePage('/')); assert(!isPrivatePage('/login-other'));
  assert.equal((await proxyAuth(request('yandex/start', { method: 'POST', headers: { Origin: 'https://rekvero.example', 'Content-Type': 'application/json' }, body: 'a'.repeat(4097) }), 'yandex/start')).status, 413);
  globalThis.fetch = async () => new Response('a'.repeat(8193), { headers: { 'Content-Type': 'application/json' } });
  assert.equal((await proxyAuth(request('yandex/start', { method: 'POST', headers: { Origin: 'https://rekvero.example', 'Content-Type': 'application/json' }, body: '{}' }), 'yandex/start')).status, 502);
  globalThis.fetch = async () => new Response(null, { status: 302, headers: { Location: 'https://evil.example' } });
  assert.equal((await proxyAuth(request('yandex/callback'), 'yandex/callback')).status, 502);
  delete process.env.ADPILOT_API_URL;
  assert.equal((await proxyAuth(request('logout', { method: 'POST', headers: { Origin: 'https://rekvero.example' } }), 'logout')).status, 503);
} finally {
  globalThis.fetch = originalFetch;
  if (previous === undefined) delete process.env.ADPILOT_API_URL;
  else process.env.ADPILOT_API_URL = previous;
}
console.log('PASS: auth proxy origin, path, method, configuration, callback, cookie, redirect and no-cache; exact legal bytes/hash/version/locale and bounded fail-closed fetching.');
