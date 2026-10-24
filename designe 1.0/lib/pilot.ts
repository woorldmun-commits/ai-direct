import 'server-only';
import { cookies } from 'next/headers';
import { apiOrigin } from './api-origin';
import { workspacePath } from './workspace-path';

export class PilotError extends Error {
  constructor(public code: 'setup' | 'session' | 'access' | 'unavailable' | 'invalid') { super(code); }
}

// Only this server module receives the session. No browser storage or client-side API credentials.
export async function pilotGet<T>(path: string, validate: (v: unknown) => v is T): Promise<T> {
  if (path !== '/me' && !workspacePath(path, 'GET')) throw new PilotError('invalid');
  const base = apiOrigin();
  if (!base) throw new PilotError('setup');
  const name = process.env.INROU_SESSION_COOKIE ?? 'session';
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(name)) throw new PilotError('setup');
  const token = (await cookies()).get(name)?.value;
  if (!token || !/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new PilotError('session');
  try {
    const response = await fetch(new URL('/api/v1' + path, base), {
      method: 'GET', headers: { Cookie: `${name}=${token}`, Accept: 'application/json' },
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(8000),
    });
    if (response.status === 401) throw new PilotError('session');
    if ([403, 404, 410].includes(response.status)) throw new PilotError('access');
    if (!response.ok) throw new PilotError('unavailable');
    if (!response.headers.get('content-type')?.includes('application/json')) throw new PilotError('invalid');
    const reader = response.body?.getReader();
    if (!reader) throw new PilotError('invalid');
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 1_048_576) throw new PilotError('invalid');
        chunks.push(value);
      }
    } finally { await reader.cancel(); }
    const joined = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.byteLength; }
    let body: unknown;
    try { body = JSON.parse(new TextDecoder().decode(joined)); } catch { throw new PilotError('invalid'); }
    if (!validate(body)) throw new PilotError('invalid');
    return body;
  } catch (error) {
    if (error instanceof PilotError) throw error;
    throw new PilotError('unavailable');
  }
}
