import { apiOrigin, appOrigin } from './api-origin';
import {proxyClientHeaders} from './proxy-client';

const responseHeaders = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' };
const failure = (status: number) => Response.json({ error: { message: 'Вход временно недоступен. Попробуйте позже.' } }, { status, headers: responseHeaders });

export async function readLimited(body: ReadableStream<Uint8Array> | null, limit: number): Promise<string> {
  if (!body) return '';
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  const deadline = Date.now() + 8000;
  try {
    for (;;) {
      let timer: ReturnType<typeof setTimeout> | undefined;
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('body_timeout')), Math.max(1, deadline - Date.now()));
      });
      const { done, value } = await Promise.race([reader.read(), timeout]).finally(() => clearTimeout(timer));
      if (done) break;
      size += value.byteLength;
      if (size > limit) throw new Error('body_limit');
      chunks.push(value);
    }
  } finally { await reader.cancel(); }
  const joined = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder().decode(joined);
}

export async function proxyAuth(request: Request, path: string): Promise<Response> {
  const callback = path === 'yandex/callback';
  const read = callback || path === 'config';
  if (!['yandex/start', 'yandex/callback', 'logout', 'config', 'email/register', 'email/login', 'email/verify', 'email/reset-request', 'email/reset'].includes(path)
    || request.method !== (read ? 'GET' : 'POST')) return failure(404);
  const incoming = new URL(request.url);
  const publicOrigin = appOrigin(request);
  if (!publicOrigin) return failure(503);
  if (!read && request.headers.get('origin') !== publicOrigin) return failure(403);
  const base = apiOrigin();
  if (!base) return failure(503);
  const target = new URL('/api/v1/auth/' + path, base);
  if (callback) {
    for (const key of ['state', 'code', 'error']) {
      const values = incoming.searchParams.getAll(key);
      if (values.length > 1 || (values[0]?.length ?? 0) > 2048) return failure(400);
      if (values[0]) target.searchParams.set(key, values[0]);
    }
  }
  const headers = new Headers({ Accept: 'application/json' });
  for(const [name,value] of Object.entries(proxyClientHeaders(request,target.pathname))) headers.set(name,value);
  const userAgent = request.headers.get('user-agent');
  if (userAgent) headers.set('User-Agent', userAgent.slice(0, 1024));
  // Forward only the cookies required by this account flow.
  const sessionName = process.env.INROU_SESSION_COOKIE ?? 'session';
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(sessionName)) return failure(503);
  const selected = (request.headers.get('cookie') || '').split(';').map(c => c.trim()).filter(c =>
    [sessionName, 'inrou_oauth_flow'].some(name => c.startsWith(name + '=')) && /^[A-Za-z0-9_-]+=[A-Za-z0-9_.=-]{1,4096}$/.test(c));
  if (selected.length) headers.set('Cookie', selected.join('; '));
  if (!read) headers.set('Origin', publicOrigin);
  let body: string | undefined;
  if (path === 'yandex/start' || path.startsWith('email/')) {
    if (!request.headers.get('content-type')?.startsWith('application/json')) return failure(415);
    if (Number(request.headers.get('content-length') || 0) > 4096) return failure(413);
    try { body = await readLimited(request.body, 4096); } catch { return failure(413); }
    headers.set('Content-Type', 'application/json');
  }
  try {
    const upstream = await fetch(target, { method: request.method, headers, body, cache: 'no-store', redirect: 'manual', signal: AbortSignal.timeout(15000) });
    const outgoing = new Headers(responseHeaders);
    for (const cookie of upstream.headers.getSetCookie()) outgoing.append('Set-Cookie', cookie);
    if ([302, 303, 307].includes(upstream.status)) {
      const location = upstream.headers.get('location');
      if (!location || !/^\/(workspace|login)(\?[^\r\n]*)?$/.test(location)) return failure(502);
      outgoing.set('Location', location);
      return new Response(null, { status: upstream.status, headers: outgoing });
    }
    if (path === 'logout' && upstream.ok) {
      outgoing.set('Location', '/login');
      return new Response(null, { status: 303, headers: outgoing });
    }
    if (!upstream.ok) return failure(upstream.status >= 400 && upstream.status <= 599 ? upstream.status : 502);
    if (!upstream.headers.get('content-type')?.includes('application/json')) return failure(502);
    let text: string;
    try { text = await readLimited(upstream.body, 8192); } catch { return failure(502); }
    outgoing.set('Content-Type', 'application/json');
    return new Response(text, { status: upstream.status, headers: outgoing });
  } catch { return failure(503); }
}
