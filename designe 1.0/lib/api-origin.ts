// Only a server-controlled origin can receive account credentials.
export function apiOrigin(configured = process.env.REKVERO_API_URL ?? process.env.ADPILOT_API_URL): URL | null {
  if (!configured) return null;
  try {
    const base = new URL(configured);
    const local = ['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname);
    if ((base.protocol !== 'https:' && !(local && base.protocol === 'http:'))
      || base.username || base.password || base.search || base.hash || base.pathname !== '/') return null;
    return base;
  } catch { return null; }
}

// Reverse proxies may give Next.js an internal URL; never trust forwarded Host as the public origin.
export function appOrigin(request: Request): string | null {
  return apiOrigin(process.env.REKVERO_APP_ORIGIN ?? process.env.ADPILOT_APP_ORIGIN ?? new URL(request.url).origin)?.origin ?? null;
}
