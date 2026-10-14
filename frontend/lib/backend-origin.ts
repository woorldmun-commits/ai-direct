export function backendOrigin(): string | undefined {
  const value = process.env.BACKEND_ORIGIN?.trim();
  if (!value) return undefined;
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('BACKEND_ORIGIN must be an HTTP(S) origin without credentials, path, query or fragment');
  }
  return url.origin;
}
