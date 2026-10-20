import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

async function load(file) {
  const source = await readFile(new URL('../lib/' + file + '.ts', import.meta.url), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  return import('data:text/javascript;base64,' + Buffer.from(output).toString('base64'));
}
const { buildCsp } = await load('csp');
const nonce = 'YXNkZmdoamtsMTIzNDU2';
assert.match(buildCsp(nonce), /script-src 'self' 'nonce-YXNkZmdoamtsMTIzNDU2' 'strict-dynamic'/);
assert.doesNotMatch(buildCsp(nonce), /script-src[^;]*'unsafe-(?:inline|eval)'/);
assert.doesNotMatch(buildCsp(nonce), /style-src [^;]*'unsafe-inline'/);
assert.match(buildCsp(nonce, false, true), /frame-src https:\/\/smartcaptcha.cloud.yandex.ru/);
assert.throws(() => buildCsp("x'; script-src *"));
const { backendOrigin } = await load('backend-origin');
const previousOrigin = process.env.BACKEND_ORIGIN;
try {
  delete process.env.BACKEND_ORIGIN;
  assert.equal(backendOrigin(), undefined);
  process.env.BACKEND_ORIGIN = 'http://127.0.0.1:8000/';
  assert.equal(backendOrigin(), 'http://127.0.0.1:8000');
  for (const invalid of ['file:///etc/passwd', 'https://user:secret@example.com', 'https://example.com/api', 'https://example.com/?x=1']) {
    process.env.BACKEND_ORIGIN = invalid;
    assert.throws(backendOrigin);
  }
} finally {
  if (previousOrigin === undefined) delete process.env.BACKEND_ORIGIN;
  else process.env.BACKEND_ORIGIN = previousOrigin;
}
const { api, ApiError } = await load('api');
const previousFetch = globalThis.fetch;
try {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/v1/auth/code/request');
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.headers.get('Content-Type'), 'application/json');
    return Response.json({ error: { code: 'captcha_required', message: 'Проверка требуется', reason: 'captcha_required' } }, { status: 429 });
  };
  await assert.rejects(api('/auth/code/request', { method: 'POST', body: '{}' }), (error) => error instanceof ApiError && error.code === 'captcha_required' && error.status === 429);
  await assert.rejects(api('//example.com'));
  globalThis.fetch = async () => new Response('', { status: 502 });
  await assert.rejects(api('/me'), (error) => error instanceof ApiError && error.code === 'unavailable');
} finally { globalThis.fetch = previousFetch; }
console.log('OK runtime: CSP, backend origin validation, API errors and same-origin credentials');
